# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, patch

import pytest
from ops.pebble import Error, ExecError

from cli import CommandLine
from constants import CONFIG_FILE_NAME
from exceptions import MigrationError


class TestCommandLine:
    @pytest.fixture
    def command_line(self, mocked_container: MagicMock) -> CommandLine:
        return CommandLine(mocked_container)

    def test_get_admin_service_version(self, command_line: CommandLine) -> None:
        expected = "v1.0.0"
        with patch.object(
            command_line,
            "_run_cmd",
            return_value=(
                f"Version:    {expected}\n"
                f"Git Hash:    e23751bbc5704efd58acc1132b987ff7fb0412ac\n"
                f"Build Time:    2024-05-01T07:49:53Z"
            ),
        ) as run_cmd:
            actual = command_line.get_hydra_service_version()
            assert actual == expected
            run_cmd.assert_called_with(["hydra", "version"])

    def test_migrate_with_dsn(self, command_line: CommandLine) -> None:
        dsn = "postgres://user:password@localhost/db"
        with patch.object(command_line, "_run_cmd") as run_cmd:
            command_line.migrate(dsn)

        expected_cmd = ["hydra", "migrate", "sql", "-e", "--yes"]
        expected_environments = {"DSN": dsn}
        run_cmd.assert_called_once_with(
            expected_cmd, timeout=60, environment=expected_environments
        )

    def test_migrate_without_dsn(self, command_line: CommandLine) -> None:
        with patch.object(command_line, "_run_cmd") as run_cmd:
            command_line.migrate()

        expected_cmd = ["hydra", "migrate", "sql", "-e", "--yes", "--config", CONFIG_FILE_NAME]
        run_cmd.assert_called_once_with(expected_cmd, timeout=60, environment=None)

    def test_migrate_failed(self, command_line: CommandLine) -> None:
        with patch.object(command_line, "_run_cmd", side_effect=Error), pytest.raises(
            MigrationError
        ):
            command_line.migrate()

    def test_get_oauth_client_not_found(self, command_line: CommandLine) -> None:
        with patch.object(
            command_line,
            "_run_cmd",
            side_effect=Error(
                '{"error": "Unable to locate the resource", "error_description": ""}'
            ),
        ):
            actual = command_line.get_oauth_client("a945ef38-76fc-41ee-8364-12a70fa6c398")

        assert actual is None

    def test_run_cmd(self, mocked_container: MagicMock, command_line: CommandLine) -> None:
        cmd, expected = ["cmd"], "stdout"

        mocked_process = MagicMock(wait_output=MagicMock(return_value=(expected, "")))
        mocked_container.exec.return_value = mocked_process

        actual = command_line._run_cmd(cmd)

        assert actual == expected
        mocked_container.exec.assert_called_once_with(cmd, timeout=20, environment=None)

    def test_run_cmd_failed(self, mocked_container: MagicMock, command_line: CommandLine) -> None:
        cmd = ["cmd"]

        mocked_process = MagicMock(wait_output=MagicMock(side_effect=ExecError(cmd, 1, "", "")))
        mocked_container.exec.return_value = mocked_process

        with pytest.raises(ExecError):
            command_line._run_cmd(cmd)
