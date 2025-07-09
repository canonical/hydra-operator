# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.


import json
import logging
import re
from typing import Any, Optional

from ops import Container
from ops.pebble import Error, ExecError
from pydantic import AliasChoices, BaseModel, Field, field_serializer, field_validator

from constants import ADMIN_PORT, CONFIG_FILE_NAME, DEFAULT_OAUTH_SCOPES, DEFAULT_RESPONSE_TYPES
from exceptions import ClientDoesNotExistError, CommandExecError, MigrationError

logger = logging.getLogger(__name__)

VERSION_REGEX = re.compile(r"Version:\s+(?P<version>v\d+\.\d+\.\d+)")


class OAuthClient(BaseModel):
    redirect_uris: Optional[list[str]] = Field(
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
        return "integration-id" in self.metadata

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

        kv = v.split(",")

        metadata = {}

        for pair in kv:
            key, value = pair.split("=")
            metadata[key] = value

        return metadata

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
        """
        cmd = ["hydra", "migrate", "sql", "-e", "--yes"]
        env_vars = {"DSN": dsn} if dsn else None

        if not dsn:
            cmd.extend(["--config", CONFIG_FILE_NAME])

        try:
            self._run_cmd(cmd, timeout=timeout, environment=env_vars)
        except Error as err:
            logger.error("Failed to migrate the hydra service: %s", err)
            raise MigrationError from err

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

        More information: https://www.ory.sh/docs/hydra/cli/hydra-get-client
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
        except Error as err:
            logger.error("Failed to get the OAuth client: %s", err)
            if "Unable to locate the resource" in str(err):
                logger.error("OAuth client not found: %s", client_id)
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
            if "Unable to locate the resource" in err.stderr:
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
    ) -> str:
        logger.debug(f"Running command: {cmd}")
        process = self.container.exec(cmd, environment=environment, timeout=timeout)
        try:
            stdout, _ = process.wait_output()
        except ExecError as err:
            logger.error("Exited with code: %d. Error: %s", err.exit_code, err.stderr)
            raise

        return stdout
