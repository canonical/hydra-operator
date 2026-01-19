# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock

import pytest
from ops import Container
from ops.pebble import ExecError

from cli import CommandLine, parse_kv_string
from exceptions import MigrationError


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

    def test_migrate_with_dsn(
        self, command_line: CommandLine, container: MagicMock, mock_process: MagicMock
    ) -> None:
        mock_process.wait_output.return_value = (None, None)

        dsn = "postgres://user:password@localhost/db"
        command_line.migrate(dsn)

        container.exec.assert_called_with(
            ["hydra", "migrate", "sql", "-e", "--yes"],
            environment={"DSN": dsn},
            timeout=60,
        )

    def test_migrate_without_dsn(
        self, command_line: CommandLine, container: MagicMock, mock_process: MagicMock
    ) -> None:
        mock_process.wait_output.return_value = (None, None)

        command_line.migrate()

        container.exec.assert_called_with(
            ["hydra", "migrate", "sql", "-e", "--yes", "--config", "/etc/config/hydra.yaml"],
            environment=None,
            timeout=60,
        )

    def test_migrate_failed(
        self, command_line: CommandLine, container: MagicMock, mock_process: MagicMock
    ) -> None:
        mock_process.wait_output.side_effect = ExecError(["cmd"], 1, "error", "")

        with pytest.raises(MigrationError):
            command_line.migrate()

    def test_get_oauth_client_not_found(
        self, command_line: CommandLine, container: MagicMock, mock_process: MagicMock
    ) -> None:
        mock_process.wait_output.side_effect = ExecError(
            ["cmd"], 1, "Unable to locate the resource", ""
        )

        actual = command_line.get_oauth_client("client_id")
        assert actual is None

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
