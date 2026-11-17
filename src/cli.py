# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.


import io
import json
import logging
import re
import shlex
from enum import Enum
from http.client import HTTPException
from typing import Annotated, Any, Literal, Optional

from ops import Container
from ops.pebble import ConnectionError as PebbleConnectionError
from ops.pebble import Error, ExecError
from pydantic import (
    AliasChoices,
    BaseModel,
    Field,
    TypeAdapter,
    ValidationError,
    field_serializer,
    field_validator,
)

from constants import ADMIN_PORT, CONFIG_FILE_NAME, DEFAULT_OAUTH_SCOPES, DEFAULT_RESPONSE_TYPES
from exceptions import ClientDoesNotExistError, CommandExecError, MigrationError

logger = logging.getLogger(__name__)

VERSION_REGEX = re.compile(r"Version:\s+(?P<version>v\d+\.\d+\.\d+)")

# The per-migration states printed by `hydra migrate sql status`
MIGRATION_STATES: TypeAdapter[list[str]] = TypeAdapter(
    Annotated[list[Literal["Applied", "Pending"]], Field(min_length=1)]
)

# Command options whose value must not be logged
SENSITIVE_OPTIONS = ("--secret",)
# The `user:password@` of a URL. A URL-encoded password holds no "/", which keeps
# a plain URL with an "@" further down its path out of the match
DSN_CREDENTIALS_REGEX = re.compile(r"(://[^:/@\s]*):[^/@\s]+@")

# Hydra starts every log record with its timestamp; a record can span several lines
LOG_RECORD_START_REGEX = re.compile(r"^(?=time=)", re.MULTILINE)
MAX_LOG_RECORD = 500
MAX_LOGGED_STDERR = 1000


class SchemaState(str, Enum):
    """State of the Hydra database schema relative to the workload binary."""

    FRESH = "fresh"  # no migration applied
    UP_TO_DATE = "up_to_date"  # no migration pending
    UPGRADE_PENDING = "upgrade_pending"  # some migrations applied, some pending


def redact_command(cmd: list[str]) -> list[str]:
    """Hide the values of the sensitive options of a command."""
    return [
        "***" if index and cmd[index - 1] in SENSITIVE_OPTIONS else arg
        for index, arg in enumerate(cmd)
    ]


def redact_dsn(text: str) -> str:
    """Hide the password of any URL-encoded DSN in a text."""
    return DSN_CREDENTIALS_REGEX.sub(r"\1:***@", text)


def error_summary(err: Exception) -> str:
    """Say in one line what failed, without the output Pebble attaches to a failed change.

    That output is what the workload printed, and Hydra prints the values it rejects.
    """
    # ChangeError.err is the summary of the change, without its task logs
    return " ".join(str(getattr(err, "err", err)).split())


def last_output(stderr: str) -> str:
    """Extract what Hydra printed last, which says why a command failed.

    The error Hydra exits with comes after its log records and is followed by a stack
    trace. When Hydra instead kept retrying an unreachable database until the command
    timed out, the last record is the last retry.
    """
    last_record = LOG_RECORD_START_REGEX.split(stderr.strip())[-1]
    first_line, _, rest = last_record.partition("\n")
    # A record continues on indented lines; the error Hydra exits with is not indented
    if first_line.startswith("time=") and rest and not rest[0].isspace():
        last_record = rest

    return redact_dsn(" ".join(last_record.split()))[:MAX_LOG_RECORD]


def failure_reason(err: Error, stderr: str) -> str:
    """Summarise why a Hydra command failed, for the logs and for action results."""
    if isinstance(err, ExecError):
        reason = f"hydra exited with code {err.exit_code}"
    else:
        reason = error_summary(err)

    if stderr.strip():
        reason = f"{reason}; last output from hydra: {last_output(stderr)}"

    return reason


def parse_kv_string(kv_str: str) -> dict[str, str]:
    """Parse a key-value string into a dictionary.

    Args:
        kv_str: A string containing key-value pairs in the format
            "key1=value1 key2=value2 ...". Values can be enclosed in single or
            double quotes to include spaces.

    Returns:
        A dictionary with keys and their corresponding values.

    Example:
        Input: "foo='bar qux' baz=quux"
        Output: {"foo": "bar qux", "baz": "quux"}

    Undefined behaviour:
        - Multiple equals signs in unquoted values (e.g., "key=value=extra").
          Currently this will parse as key="key" and value="value=extra",
          however this behavior is not guaranteed and may change in the future.
    """
    result = {}
    parts = shlex.split(kv_str)

    for part in parts:
        if "=" in part:
            key, value = part.split("=", 1)
            result[key] = value
        else:
            raise ValueError(
                f"Invalid key-value pair: '{part}'. Expected format 'key=value' (values with spaces should be quoted)."
            )

    return result


class OAuthClient(BaseModel):
    redirect_uris: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("redirect-uris", "redirect_uris", "redirect_uri"),
        serialization_alias="redirect-uris",
    )
    response_types: list[str] = Field(
        default=DEFAULT_RESPONSE_TYPES,
        validation_alias=AliasChoices("response-types", "response_types"),
        serialization_alias="response-types",
    )
    scope: str = ",".join(DEFAULT_OAUTH_SCOPES)
    token_endpoint_auth_method: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("token-endpoint-auth-method", "token_endpoint_auth_method"),
        serialization_alias="token-endpoint-auth-method",
    )
    metadata: Optional[dict[str, Any]] = Field(default_factory=dict)
    audience: Optional[list[str]] = None
    client_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("client-id", "client_id"),
        serialization_alias="client-id",
    )
    client_secret: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("client-secret", "client_secret"),
        serialization_alias="client-secret",
    )
    grant_types: Optional[list[str]] = Field(
        default=None,
        validation_alias=AliasChoices("grant-types", "grant_types"),
        serialization_alias="grant-types",
    )
    name: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("client-name", "client_name", "name"),
        serialization_alias="name",
    )
    contacts: Optional[list[str]] = Field(
        default_factory=list,
        serialization_alias="contacts",
    )
    client_uri: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("client-uri", "client_uri"),
        serialization_alias="client-uri",
    )

    @property
    def managed_by_integration(self) -> bool:
        return "integration-id" in (self.metadata or {})

    @field_validator("redirect_uris", mode="before")
    @classmethod
    def deserialize_redirect_uris(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, list):
            return v

        return v.split()

    @field_validator("scope", mode="before")
    @classmethod
    def deserialize_scope(cls, v: str | list[str]) -> str:
        if isinstance(v, str):
            return v

        return ",".join(v)

    @field_serializer("scope")
    def serialize_scope(self, scope: str) -> list[str]:
        return scope.split()

    @field_validator("metadata", mode="before")
    @classmethod
    def deserialize_metadata(cls, v: str | dict[str, Any]) -> dict[str, Any]:
        if isinstance(v, dict):
            return v
        return parse_kv_string(v)

    def to_cmd_options(self) -> list[str]:
        cmd_options = []

        cmd_options.extend(["--scope", self.scope])
        cmd_options.extend(["--response-type", ",".join(self.response_types)])

        if self.audience:
            cmd_options.extend(["--audience", ",".join(self.audience)])

        if self.name:
            cmd_options.extend(["--name", self.name])

        if self.client_uri:
            cmd_options.extend(["--client-uri", self.client_uri])

        if self.contacts:
            cmd_options.extend(["--contact", ",".join(self.contacts)])

        if self.grant_types:
            cmd_options.extend(["--grant-type", ",".join(self.grant_types)])

        if self.redirect_uris:
            cmd_options.extend(["--redirect-uri", ",".join(self.redirect_uris)])

        if self.client_secret:
            cmd_options.extend(["--secret", self.client_secret])

        if self.token_endpoint_auth_method:
            cmd_options.extend(["--token-endpoint-auth-method", self.token_endpoint_auth_method])

        if self.metadata:
            cmd_options.extend(["--metadata", json.dumps(self.metadata)])

        return cmd_options


class CommandLine:
    def __init__(self, container: Container):
        self.container = container

    def get_hydra_service_version(self) -> Optional[str]:
        """Get Hydra application version.

        Version command output format:
        Version:    {version}
        Git Hash:   {hash}
        Build Time: {time}
        """
        cmd = ["hydra", "version"]
        try:
            stdout = self._run_cmd(cmd)
        except Error as err:
            logger.error("Failed to fetch the hydra version: %s", err)
            return None

        matched = VERSION_REGEX.search(stdout)
        return matched.group("version") if matched else None

    def migrate(self, dsn: Optional[str] = None, timeout: float = 60) -> None:
        """Apply Hydra migration plan.

        More information: https://www.ory.sh/docs/hydra/cli/hydra-migrate-sql

        Raises:
            MigrationError: if the migration failed, with the reason as its message.
        """
        cmd = ["hydra", "migrate", "sql", "up", "-e", "--yes"]
        env_vars = {"DSN": dsn} if dsn else None

        if not dsn:
            cmd.extend(["--config", CONFIG_FILE_NAME])

        stderr = io.StringIO()
        try:
            self._run_cmd(cmd, timeout=timeout, environment=env_vars, stderr=stderr)
        except Error as err:
            reason = failure_reason(err, stderr.getvalue())
            logger.error("Failed to migrate the hydra service: %s", reason)
            raise MigrationError(reason) from err

    def migration_status(self, dsn: str, timeout: float = 20) -> SchemaState:
        """Inspect which migrations of this Hydra binary are applied to the database.

        The jsonpath format keeps only the per-migration state; the default JSON
        output embeds every migration's SQL. Hydra retries an unreachable database
        forever, so the exec timeout bounds the call.

        More information (the page documents the deprecated `hydra migrate status`
        alias, which takes the same flags):
        https://www.ory.com/docs/hydra/cli/hydra-migrate-status

        Raises:
            MigrationError: if the status could not be fetched, or if the output is
                anything but a non-empty list of known states. The reason is its message.
        """
        cmd = ["hydra", "migrate", "sql", "status", "-e", "--format", "jsonpath=#.state"]

        stderr = io.StringIO()
        try:
            stdout = self._run_cmd(cmd, timeout=timeout, environment={"DSN": dsn}, stderr=stderr)
        except Error as err:
            reason = failure_reason(err, stderr.getvalue())
            # Callers retry, and the database may just not be reachable yet.
            logger.warning("Failed to get the hydra migration status: %s", reason)
            raise MigrationError(reason) from err

        # An unknown state must not pass for an up-to-date schema.
        try:
            states = MIGRATION_STATES.validate_json(stdout)
        except ValidationError as err:
            logger.error("Unexpected hydra migration status output: %s", stdout)
            raise MigrationError("unexpected hydra migration status output") from err

        if "Pending" not in states:
            return SchemaState.UP_TO_DATE
        if "Applied" not in states:
            return SchemaState.FRESH
        return SchemaState.UPGRADE_PENDING

    def create_jwk(
        self, key_set_id: str = "hydra.openid.id-token", algorithm: str = "RS256"
    ) -> Optional[str]:
        """Create a new JSON Web Key.

        More information: https://www.ory.sh/docs/hydra/cli/hydra-create-jwk
        """
        cmd = [
            "hydra",
            "create",
            "jwk",
            key_set_id,
            "--endpoint",
            f"http://localhost:{ADMIN_PORT}",
            "--format",
            "json",
            "--alg",
            algorithm,
        ]

        try:
            stdout = self._run_cmd(cmd)
        except Error as err:
            logger.error("Failed to create a JSON Web Key: %s", err)
            return None

        res = json.loads(stdout)
        return res["keys"][0]["kid"]

    def list_oauth_clients(self) -> list[OAuthClient]:
        """List OAuth 2.0 clients.

        More information: https://www.ory.sh/docs/hydra/cli/hydra-list-clients
        """
        cmd = [
            "hydra",
            "list",
            "clients",
            "--endpoint",
            f"http://localhost:{ADMIN_PORT}",
            "--format",
            "json",
        ]

        try:
            stdout = self._run_cmd(cmd)
        except Error as err:
            logger.error("Failed to list all OAuth clients: %s", err)
            return []

        clients = json.loads(stdout)["items"]
        return [OAuthClient(**c) for c in clients]

    def get_oauth_client(self, client_id: str) -> Optional[OAuthClient]:
        """Get an OAuth 2.0 client by client id.

        Returns None when the client could not be fetched. A caller that must not confuse
        "Hydra does not have it" with "the lookup failed" should catch the exception rather
        than test for None.

        More information: https://www.ory.sh/docs/hydra/cli/hydra-get-client

        Raises:
            ClientDoesNotExistError: if Hydra reports that the client is not registered.
        """
        cmd = [
            "hydra",
            "get",
            "client",
            client_id,
            "--endpoint",
            f"http://localhost:{ADMIN_PORT}",
            "--format",
            "json",
        ]

        try:
            stdout = self._run_cmd(cmd)
        except ExecError as err:
            logger.error("Failed to get the OAuth client: %s", err)
            if err.stderr and "Unable to locate the resource" in err.stderr:
                raise ClientDoesNotExistError() from err
            return None
        except Error as err:
            logger.error("Failed to get the OAuth client: %s", err)
            return None

        return OAuthClient.model_validate_json(stdout)

    def create_oauth_client(self, client: OAuthClient) -> Optional[OAuthClient]:
        """Create an OAuth 2.0 client.

        More information: https://www.ory.sh/docs/hydra/cli/hydra-create-client
        """
        cmd_options = client.to_cmd_options()

        cmd = [
            "hydra",
            "create",
            "client",
            "--endpoint",
            f"http://localhost:{ADMIN_PORT}",
            "--format",
            "json",
        ]

        try:
            stdout = self._run_cmd(cmd + cmd_options)
        except Error as err:
            logger.error("Failed to create an OAuth client: %s", err)
            return None

        return OAuthClient.model_validate_json(stdout)

    def update_oauth_client(self, client: OAuthClient) -> Optional[OAuthClient]:
        """Update an OAuth client by client id.

        More information: https://www.ory.sh/docs/hydra/cli/hydra-update-client
        """
        cmd_options = client.to_cmd_options()

        cmd = [
            "hydra",
            "update",
            "client",
            client.client_id,
            "--endpoint",
            f"http://localhost:{ADMIN_PORT}",
            "--format",
            "json",
        ]

        try:
            stdout = self._run_cmd(cmd + cmd_options)  # type: ignore[arg-type]
        except Error as err:
            logger.error("Failed to update an OAuth client: %s", err)
            return None

        return OAuthClient.model_validate_json(stdout)

    def delete_oauth_client(self, client_id: str) -> Optional[str]:
        """Delete an OAuth client by client id.

        More information: https://www.ory.sh/docs/hydra/cli/hydra-delete-client
        """
        cmd = [
            "hydra",
            "delete",
            "client",
            client_id,
            "--endpoint",
            f"http://localhost:{ADMIN_PORT}",
            "--format",
            "json",
        ]

        try:
            stdout = self._run_cmd(cmd)
        except ExecError as err:
            logger.error("Failed to delete an OAuth client: %s", err)
            if err.stderr and "Unable to locate the resource" in err.stderr:
                raise ClientDoesNotExistError()
            raise CommandExecError() from err

        return json.loads(stdout)  # client id

    def delete_oauth_client_access_tokens(self, client_id: str) -> Optional[str]:
        """Delete all access tokens of an OAuth client.

        More information: https://www.ory.sh/docs/hydra/cli/hydra-delete-access-tokens
        """
        cmd = [
            "hydra",
            "delete",
            "access-tokens",
            client_id,
            "--endpoint",
            f"http://localhost:{ADMIN_PORT}",
            "--format",
            "json",
        ]

        try:
            stdout = self._run_cmd(cmd)
        except Error as err:
            logger.error("Failed to delete access tokens: %s", err)
            return None

        return json.loads(stdout)  # client id

    def _run_cmd(
        self,
        cmd: list[str],
        timeout: float = 20,
        environment: Optional[dict] = None,
        stderr: io.StringIO | None = None,
    ) -> str:
        """Run a command in the workload container and return its stdout.

        With `stderr`, the output is streamed and stderr is collected into it, so that
        what was printed is still available when the command fails or times out. The
        caller then reports the failure.
        """
        logger.debug("Running command: %s", redact_command(cmd))
        try:
            if stderr is None:
                process = self.container.exec(cmd, environment=environment, timeout=timeout)
                stdout, _ = process.wait_output()
            else:
                output = io.StringIO()
                process = self.container.exec(
                    cmd, environment=environment, timeout=timeout, stdout=output, stderr=stderr
                )
                process.wait()
                stdout = output.getvalue()
        except ExecError as err:
            if stderr is None:
                error_output = redact_dsn(err.stderr or "")
                if len(error_output) > MAX_LOGGED_STDERR:
                    error_output = f"{error_output[:MAX_LOGGED_STDERR]} [truncated]"
                logger.error("Exited with code: %d. Error: %s", err.exit_code, error_output)
            raise
        except Error:
            raise
        except (OSError, HTTPException) as err:
            # ops does not wrap a connection that drops while a request is in flight,
            # e.g. when the container restarts during the command
            raise PebbleConnectionError(f"Lost the connection to Pebble: {err}") from err

        return stdout
