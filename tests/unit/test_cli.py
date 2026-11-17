# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import io
import json
import logging
from http.client import RemoteDisconnected
from unittest.mock import MagicMock

import pytest
from ops import Container
from ops.pebble import ChangeError, ConnectionError, ExecError, TimeoutError

from cli import (
    CommandLine,
    OAuthClient,
    SchemaState,
    last_output,
    parse_kv_string,
    redact_command,
    redact_dsn,
)
from exceptions import ClientDoesNotExistError, MigrationError


@pytest.mark.parametrize(
    "input_str,expected",
    [
        # Simple single key-value pair
        ("foo=bar", {"foo": "bar"}),
        # Multiple key-value pairs
        ("foo=bar baz=qux", {"foo": "bar", "baz": "qux"}),
        # Single quoted value with space
        ("foo='bar qux' baz=quux", {"foo": "bar qux", "baz": "quux"}),
        # Multiple single quoted values with spaces
        ("foo='bar qux' baz='quux quuz'", {"foo": "bar qux", "baz": "quux quuz"}),
        # Single quoted value containing equals sign
        ("foo='bar=qux' baz=quux", {"foo": "bar=qux", "baz": "quux"}),
        # Mix of unquoted and quoted values
        (
            "foo=bar baz='qux quux' corge='grault garply'",
            {"foo": "bar", "baz": "qux quux", "corge": "grault garply"},
        ),
        # Key without value (implicit empty string)
        ("foo=bar baz=qux quux=", {"foo": "bar", "baz": "qux", "quux": ""}),
        # Explicit empty value
        ("foo=bar baz=", {"foo": "bar", "baz": ""}),
        # Mix of single and double quotes
        ("foo='bar' baz=\"qux\"", {"foo": "bar", "baz": "qux"}),
        # # Unquoted value containing equals sign
        # ("foo=bar=baz", {"foo": "bar=baz"}),
        # All values single quoted with spaces
        (
            "foo='bar qux' baz='quux quuz' corge='grault garply'",
            {"foo": "bar qux", "baz": "quux quuz", "corge": "grault garply"},
        ),
        # Empty quoted values
        ("foo='' bar=\"\"", {"foo": "", "bar": ""}),
        # Escaped double quote in value
        ('foo=bar baz="q\\"ux"', {"foo": "bar", "baz": 'q"ux'}),
        # Leading and trailing spaces in quoted value
        ("foo='  bar  ' baz=\"  qux  \"", {"foo": "  bar  ", "baz": "  qux  "}),
        # Special characters in quoted values
        ("foo='bar,qux' baz='quux;quuz'", {"foo": "bar,qux", "baz": "quux;quuz"}),
        # Undefined (due to increased complexity):
        # Multiple equals signs in unquoted value
        # "foo=bar=baz"
    ],
)
def test_key_value_parser(input_str: str, expected: dict[str, str]) -> None:
    assert parse_kv_string(input_str) == expected


def test_key_value_parser_missing_equals() -> None:
    with pytest.raises(ValueError):
        parse_kv_string("foobar")


def test_redact_command() -> None:
    cmd = ["hydra", "create", "client", "--secret", "s3cr3t", "--name", "app"]

    assert redact_command(cmd) == ["hydra", "create", "client", "--secret", "***", "--name", "app"]
    assert cmd[4] == "s3cr3t"


@pytest.mark.parametrize(
    "text, expected",
    [
        (
            'cannot parse "postgres://user:pa%2Fss@host:5432/db?sslmode=disable": invalid port',
            'cannot parse "postgres://user:***@host:5432/db?sslmode=disable": invalid port',
        ),
        ("failed to connect to `user=u database=d`", "failed to connect to `user=u database=d`"),
        ("see http://localhost:4445/health/ready", "see http://localhost:4445/health/ready"),
        (
            "GET http://localhost:4445/admin/clients/user@example.com",
            "GET http://localhost:4445/admin/clients/user@example.com",
        ),
    ],
)
def test_redact_dsn(text: str, expected: str) -> None:
    assert redact_dsn(text) == expected


@pytest.mark.parametrize(
    "stderr, expected",
    [
        (
            "time=1 level=info msg=No tracer configured\n"
            "Could not apply migrations:\n"
            "ERROR: permission denied for schema public\n",
            "Could not apply migrations: ERROR: permission denied for schema public",
        ),
        (
            "time=1 msg=> networks applied successfully\n"
            "time=2 msg=> clients applied successfully\n"
            "Could not apply migrations:\n"
            "ERROR: relation already exists\n",
            "Could not apply migrations: ERROR: relation already exists",
        ),
        (
            "time=1 msg=Retrying in 5 seconds... error=first attempt\n"
            "time=2 msg=Retrying in 5 seconds... error=failed to connect:\n"
            "\tlookup host: no such host]\n",
            "time=2 msg=Retrying in 5 seconds... error=failed to connect: "
            "lookup host: no such host]",
        ),
        ("time=1 msg=Retrying in 5 seconds...\n", "time=1 msg=Retrying in 5 seconds..."),
        ("something went wrong\n", "something went wrong"),
    ],
    ids=["exit", "exit-after-progress", "retry-on-two-lines", "retry", "no-records"],
)
def test_last_output(stderr: str, expected: str) -> None:
    assert last_output(stderr) == expected


def test_last_output_hides_a_password_that_the_bound_would_cut() -> None:
    stderr = "x" * 475 + " postgres://user:s3cr3t-passw0rd@host/db"

    assert "s3cr3t" not in last_output(stderr)


class TestCommandLine:
    @pytest.fixture
    def container(self) -> MagicMock:
        return MagicMock(spec=Container)

    @pytest.fixture
    def mock_process(self, container: MagicMock) -> MagicMock:
        process = MagicMock()
        container.exec.return_value = process
        return process

    @pytest.fixture
    def command_line(self, container: MagicMock) -> CommandLine:
        return CommandLine(container)

    @staticmethod
    def stream(
        container: MagicMock, stdout: str = "", stderr: str = "", error: Exception | None = None
    ) -> None:
        """Make the container run a command whose output is streamed, as the migrations are."""
        output, error_output = stdout, stderr

        def exec_(
            cmd: list[str], *, stdout: io.StringIO, stderr: io.StringIO, **kwargs: object
        ) -> MagicMock:
            stdout.write(output)
            stderr.write(error_output)
            process = MagicMock()
            process.wait.side_effect = error
            return process

        container.exec.side_effect = exec_

    def test_get_admin_service_version(
        self, command_line: CommandLine, container: MagicMock, mock_process: MagicMock
    ) -> None:
        mock_process.wait_output.return_value = (
            "Version:    v1.0.0\nGit Hash:   43214dsfasdf431\nBuild Time: 2024-01-01T00:00:00Z",
            None,
        )

        expected = "v1.0.0"
        actual = command_line.get_hydra_service_version()
        assert actual == expected
        container.exec.assert_called_with(["hydra", "version"], environment=None, timeout=20)

    def test_migrate_with_dsn(self, command_line: CommandLine, container: MagicMock) -> None:
        self.stream(container)

        dsn = "postgres://user:password@localhost/db"
        command_line.migrate(dsn)

        container.exec.assert_called_once()
        assert container.exec.call_args.args == (["hydra", "migrate", "sql", "up", "-e", "--yes"],)
        assert container.exec.call_args.kwargs["environment"] == {"DSN": dsn}
        assert container.exec.call_args.kwargs["timeout"] == 60

    def test_migrate_without_dsn(self, command_line: CommandLine, container: MagicMock) -> None:
        self.stream(container)

        command_line.migrate()

        assert container.exec.call_args.args == (
            ["hydra", "migrate", "sql", "up", "-e", "--yes", "--config", "/etc/config/hydra.yaml"],
        )
        assert container.exec.call_args.kwargs["environment"] is None

    def test_migrate_failed(
        self,
        command_line: CommandLine,
        container: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Hydra follows the error it exits with by a stack trace of several kilobytes."""
        self.stream(
            container,
            stderr=(
                "time=1 level=info msg=No tracer configured\n"
                "Could not apply migrations:\n"
                "ERROR: permission denied for schema public\n" + "stack frame\n" * 1000
            ),
            error=ExecError(["hydra"], 1, None, None),
        )

        with pytest.raises(MigrationError) as raised:
            command_line.migrate()

        reason = str(raised.value)
        assert reason.startswith(
            "hydra exited with code 1; last output from hydra: "
            "Could not apply migrations: ERROR: permission denied for schema public"
        )
        assert len(reason) < 600
        # The caller reports a streamed command, once
        errors = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
        assert errors == [f"Failed to migrate the hydra service: {reason}"]

    def test_logged_error_output_is_bounded(
        self,
        command_line: CommandLine,
        mock_process: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        stderr = "ERROR: something failed\n" + "stack frame\n" * 1000
        mock_process.wait_output.side_effect = ExecError(["hydra"], 1, "", stderr)

        assert command_line.get_hydra_service_version() is None

        (message,) = [m for m in caplog.messages if m.startswith("Exited with code")]
        assert message.startswith("Exited with code: 1. Error: ERROR: something failed")
        assert message.endswith("[truncated]")
        assert len(message) < 1100

    def test_logged_error_output_hides_a_password_that_the_bound_would_cut(
        self,
        command_line: CommandLine,
        mock_process: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        stderr = "x" * 975 + " postgres://user:s3cr3t-passw0rd@host/db"
        mock_process.wait_output.side_effect = ExecError(["hydra"], 1, "", stderr)

        command_line.delete_oauth_client_access_tokens("client_id")

        (message,) = [m for m in caplog.messages if m.startswith("Exited with code")]
        assert "postgres://user:***@" in message
        assert "s3cr3t" not in message

    def test_dsn_password_is_not_logged(
        self,
        command_line: CommandLine,
        container: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Hydra prints the DSN it was given when it cannot parse it."""
        self.stream(
            container,
            stderr=(
                "time=1 level=error msg=Unable to initialize service registry. "
                'error=cannot parse "postgres://user:pa%2Fss@host:5432/db": invalid port\n'
            ),
            error=ExecError(["hydra"], 1, None, None),
        )

        with pytest.raises(MigrationError):
            command_line.migration_status("postgres://user:pa%2Fss@host:5432/db")

        assert "postgres://user:***@host:5432/db" in caplog.text
        assert "pa%2Fss" not in caplog.text

    def test_migrate_timeout_reports_the_last_output(
        self, command_line: CommandLine, container: MagicMock
    ) -> None:
        """Hydra retries an unreachable database, and only its last record says why."""
        self.stream(
            container,
            stderr=(
                "time=1 msg=Retrying in 5 seconds... error=first attempt\n"
                "time=2 msg=Retrying in 5 seconds... error=failed to connect to\n"
                '\t"postgres://user:pa%2Fss@host/db": no such host\n'
            ),
            error=ChangeError(
                "cannot perform the following tasks:\n- timed out after 60s",
                MagicMock(tasks=[MagicMock(log=["output of the service"])]),
            ),
        )

        with pytest.raises(MigrationError) as raised:
            command_line.migrate("dsn")

        assert str(raised.value) == (
            "cannot perform the following tasks: - timed out after 60s; last output from hydra: "
            "time=2 msg=Retrying in 5 seconds... error=failed to connect to "
            '"postgres://user:***@host/db": no such host'
        )

    def test_migrate_reason_is_bounded(
        self, command_line: CommandLine, container: MagicMock
    ) -> None:
        self.stream(
            container,
            stderr="unexpected output " * 500,
            error=ChangeError("timed out after 60s", MagicMock()),
        )

        with pytest.raises(MigrationError) as raised:
            command_line.migrate("dsn")

        assert len(str(raised.value)) < 600

    def test_migrate_connection_error(
        self, command_line: CommandLine, container: MagicMock
    ) -> None:
        container.exec.side_effect = ConnectionError("socket not found")

        with pytest.raises(MigrationError):
            command_line.migrate()

    @pytest.mark.parametrize(
        "states, expected",
        [
            (["Pending", "Pending"], SchemaState.FRESH),
            (["Applied", "Applied"], SchemaState.UP_TO_DATE),
            (["Applied", "Pending"], SchemaState.UPGRADE_PENDING),
        ],
    )
    def test_migration_status(
        self,
        command_line: CommandLine,
        container: MagicMock,
        states: list[str],
        expected: SchemaState,
    ) -> None:
        self.stream(container, stdout=json.dumps(states))

        assert command_line.migration_status("dsn") == expected
        assert container.exec.call_args.args == (
            ["hydra", "migrate", "sql", "status", "-e", "--format", "jsonpath=#.state"],
        )
        assert container.exec.call_args.kwargs["environment"] == {"DSN": "dsn"}
        assert container.exec.call_args.kwargs["timeout"] == 20

    @pytest.mark.parametrize(
        "output, error",
        [
            ("", ExecError(["hydra"], 1, None, None)),
            ("not json", None),
            ("[]", None),
            ('{"state": "Applied"}', None),
            ('["Unknown"]', None),
            ('["Applied", "Unknown"]', None),
        ],
    )
    def test_migration_status_failed(
        self,
        command_line: CommandLine,
        container: MagicMock,
        output: str,
        error: ExecError | None,
    ) -> None:
        self.stream(container, stdout=output, error=error)

        with pytest.raises(MigrationError) as raised:
            command_line.migration_status("dsn")

        assert str(raised.value)

    def test_migration_status_timeout_is_not_logged_as_error(
        self,
        command_line: CommandLine,
        container: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        self.stream(
            container,
            stderr="msg=Retrying in 5 seconds... error=no such host\n",
            error=ChangeError("timed out after 20s", MagicMock()),
        )

        with caplog.at_level("WARNING"), pytest.raises(MigrationError):
            command_line.migration_status("dsn")

        assert [record.levelname for record in caplog.records] == ["WARNING"]
        assert "no such host" in caplog.records[0].getMessage()

    def test_migration_status_connection_error(
        self, command_line: CommandLine, container: MagicMock
    ) -> None:
        container.exec.side_effect = ConnectionError("socket not found")

        with pytest.raises(MigrationError):
            command_line.migration_status("dsn")

    @pytest.mark.parametrize(
        "error",
        [RemoteDisconnected("Remote end closed connection without response"), BrokenPipeError()],
    )
    def test_connection_dropped_during_command(
        self, command_line: CommandLine, mock_process: MagicMock, error: Exception
    ) -> None:
        """A connection ops does not wrap is handled like any other Pebble error."""
        mock_process.wait.side_effect = error
        mock_process.wait_output.side_effect = error

        with pytest.raises(MigrationError):
            command_line.migration_status("dsn")
        with pytest.raises(MigrationError):
            command_line.migrate()
        assert command_line.get_hydra_service_version() is None

    def test_pebble_error_is_raised_as_is(
        self, command_line: CommandLine, mock_process: MagicMock
    ) -> None:
        """A Pebble timeout is an OSError too, and must not pass for a dropped connection."""
        mock_process.wait_output.side_effect = TimeoutError("timed out waiting for change")

        with pytest.raises(TimeoutError):
            command_line.delete_oauth_client("client_id")

    def test_client_secret_is_not_logged(
        self,
        command_line: CommandLine,
        mock_process: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        mock_process.wait_output.side_effect = ExecError(["hydra"], 1, "", "boom")
        client = OAuthClient(client_id="client_id", client_secret="s3cr3t-value")

        with caplog.at_level(logging.DEBUG):
            command_line.create_oauth_client(client)
            command_line.update_oauth_client(client)

        assert "Running command" in caplog.text
        assert "s3cr3t-value" not in caplog.text

    def test_get_oauth_client_not_found(
        self, command_line: CommandLine, container: MagicMock, mock_process: MagicMock
    ) -> None:
        """Hydra reporting the client as missing must be distinguishable from a failure."""
        mock_process.wait_output.side_effect = ExecError(
            ["cmd"], 1, "", "Unable to locate the resource"
        )

        with pytest.raises(ClientDoesNotExistError):
            command_line.get_oauth_client("client_id")

    def test_get_oauth_client_lookup_failed(
        self, command_line: CommandLine, container: MagicMock, mock_process: MagicMock
    ) -> None:
        """An inconclusive answer must not be reported as absence."""
        mock_process.wait_output.side_effect = ExecError(["cmd"], 1, "", "connection refused")

        assert command_line.get_oauth_client("client_id") is None

    def test_run_cmd(
        self, command_line: CommandLine, container: MagicMock, mock_process: MagicMock
    ) -> None:
        mock_process.wait_output.return_value = ("out", None)

        actual = command_line._run_cmd(["cmd"])
        assert actual == "out"

    def test_run_cmd_failed(
        self, command_line: CommandLine, container: MagicMock, mock_process: MagicMock
    ) -> None:
        mock_process.wait_output.side_effect = ExecError(["cmd"], 1, "", "")

        with pytest.raises(ExecError):
            command_line._run_cmd(["cmd"])
