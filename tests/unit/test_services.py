# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock

import pytest
from ops.model import Container, ModelError, Unit
from ops.pebble import CheckStatus

from configs import ConfigFile
from constants import (
    CONFIG_FILE_NAME,
    PEBBLE_READY_CHECK_NAME,
    WORKLOAD_SERVICE,
)
from env_vars import DEFAULT_CONTAINER_ENV, EnvVarConvertible
from services import PebbleService, WorkloadService


class TestWorkloadService:
    @pytest.fixture
    def mock_container(self) -> MagicMock:
        return MagicMock(spec=Container)

    @pytest.fixture
    def mock_unit(self, mock_container: MagicMock) -> MagicMock:
        unit = MagicMock(spec=Unit)
        unit.get_container.return_value = mock_container
        return unit

    @pytest.fixture
    def workload_service(self, mock_unit: MagicMock) -> WorkloadService:
        return WorkloadService(mock_unit)

    @pytest.mark.parametrize(
        "stdout, expected",
        [
            ("Version:    v1.0.0", "v1.0.0"),
            ("Invalid", ""),
        ],
    )
    def test_get_version(
        self,
        mock_container: MagicMock,
        workload_service: WorkloadService,
        stdout: str,
        expected: str,
    ) -> None:
        mock_exec = MagicMock()
        mock_exec.wait_output.return_value = (stdout, "")
        mock_container.exec.return_value = mock_exec

        assert workload_service.version == expected

    def test_open_port(self, mock_unit: MagicMock, workload_service: WorkloadService) -> None:
        workload_service.open_port()

        assert mock_unit.open_port.call_count == 2

    def test_version_setter(self, mock_unit: MagicMock, workload_service: WorkloadService) -> None:
        workload_service.version = "v1.2.3"
        mock_unit.set_workload_version.assert_called_with("v1.2.3")

    def test_get_service(
        self, mock_container: MagicMock, workload_service: WorkloadService
    ) -> None:
        mock_service = MagicMock()
        mock_container.get_service.return_value = mock_service

        assert workload_service.get_service() == mock_service

    def test_is_running_true(
        self, mock_container: MagicMock, workload_service: WorkloadService
    ) -> None:
        mock_service = MagicMock()
        mock_service.is_running.return_value = True
        mock_container.get_service.return_value = mock_service

        mock_check = MagicMock()
        mock_check.status = CheckStatus.UP
        mock_container.get_checks.return_value = {PEBBLE_READY_CHECK_NAME: mock_check}

        assert workload_service.is_running() is True

    @pytest.mark.parametrize(
        "service_running, check_status, expected",
        [
            (False, CheckStatus.UP, False),
            (True, CheckStatus.DOWN, False),
            (True, CheckStatus.UP, True),
        ],
    )
    def test_is_running_variations(
        self,
        mock_container: MagicMock,
        workload_service: WorkloadService,
        service_running: bool,
        check_status: CheckStatus,
        expected: bool,
    ) -> None:
        mock_service = MagicMock()
        mock_service.is_running.return_value = service_running
        mock_container.get_service.return_value = mock_service

        mock_check = MagicMock()
        mock_check.status = check_status
        mock_container.get_checks.return_value = {PEBBLE_READY_CHECK_NAME: mock_check}

        assert workload_service.is_running() == expected

    def test_is_running_no_service(
        self, mock_container: MagicMock, workload_service: WorkloadService
    ) -> None:
        mock_container.get_service.side_effect = ModelError

        assert workload_service.is_running() is False

    @pytest.mark.parametrize(
        "failures, expected",
        [
            (3, True),
            (0, False),
        ],
    )
    def test_is_failing(
        self,
        mock_container: MagicMock,
        workload_service: WorkloadService,
        failures: int,
        expected: bool,
    ) -> None:
        mock_service = MagicMock()
        mock_container.get_service.return_value = mock_service

        mock_check = MagicMock()
        mock_check.failures = failures
        mock_container.get_checks.return_value = {PEBBLE_READY_CHECK_NAME: mock_check}

        assert workload_service.is_failing() == expected


class TestPebbleService:
    @pytest.fixture
    def mock_container(self) -> MagicMock:
        return MagicMock(spec=Container)

    @pytest.fixture
    def mock_unit(self, mock_container: MagicMock) -> MagicMock:
        unit = MagicMock(spec=Unit)
        unit.get_container.return_value = mock_container
        return unit

    @pytest.fixture
    def pebble_service(self, mock_unit: MagicMock) -> PebbleService:
        return PebbleService(mock_unit)

    def test_plan_when_config_files_mismatch(
        self, mock_container: MagicMock, pebble_service: PebbleService
    ) -> None:
        # Simulate local config file
        mock_file_cm = MagicMock()
        mock_file_cm.__enter__.return_value.read.return_value = "old_config"
        mock_container.pull.return_value = mock_file_cm

        layer = {"services": {"hydra": {"override": "replace"}}}

        # We invoke plan with new content
        pebble_service.plan(layer, config_file=ConfigFile("new_config"))

        # Expect push and restart because mismatch
        mock_container.push.assert_called_with(CONFIG_FILE_NAME, "new_config", make_dirs=True)
        mock_container.restart.assert_called_with(WORKLOAD_SERVICE)

    def test_plan_when_config_files_match(
        self, mock_container: MagicMock, pebble_service: PebbleService
    ) -> None:
        # Simulate local config file matching new config
        mock_file_cm = MagicMock()
        mock_file_cm.__enter__.return_value.read.return_value = "config_file"
        mock_container.pull.return_value = mock_file_cm

        layer = {"services": {"hydra": {"override": "replace"}}}

        pebble_service.plan(layer, config_file=ConfigFile("config_file"))

        # Expect replan, NO push or restart
        mock_container.push.assert_not_called()
        mock_container.restart.assert_not_called()
        mock_container.replan.assert_called_once()

    def test_render_pebble_layer(self, pebble_service: PebbleService) -> None:
        data_source = MagicMock(spec=EnvVarConvertible)
        data_source.to_env_vars.return_value = {"key1": "value1"}

        another_data_source = MagicMock(spec=EnvVarConvertible)
        another_data_source.to_env_vars.return_value = {"key2": "value2"}

        expected_env_vars = {
            **DEFAULT_CONTAINER_ENV,
            "key1": "value1",
            "key2": "value2",
        }

        layer = pebble_service.render_pebble_layer(data_source, another_data_source)

        layer_dict = layer.to_dict()
        assert layer_dict["services"][WORKLOAD_SERVICE]["environment"] == expected_env_vars

    def test_stop(self, mock_container: MagicMock, pebble_service: PebbleService) -> None:
        pebble_service.stop()

        mock_container.stop.assert_called_with(WORKLOAD_SERVICE)
