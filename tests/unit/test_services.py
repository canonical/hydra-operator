# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock

import pytest
from ops.model import Container, ModelError, Unit
from ops.pebble import ChangeError, CheckStatus, ConnectionError, ServiceStatus

from configs import ConfigFile
from constants import (
    CONFIG_FILE_NAME,
    PEBBLE_ALIVE_CHECK_NAME,
    PEBBLE_READY_CHECK_NAME,
    WORKLOAD_SERVICE,
)
from env_vars import DEFAULT_CONTAINER_ENV, EnvVarConvertible
from exceptions import PebbleServiceError
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

    @pytest.mark.parametrize(
        "stdout, expected",
        [("Version:    v1.0.0", "v1.0.0"), ("Invalid", "")],
        ids=["known", "unknown"],
    )
    def test_version_is_looked_up_once(
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
        assert workload_service.version == expected
        assert mock_container.exec.call_count == 1

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

    def test_get_service_when_pebble_is_unreachable(
        self, mock_container: MagicMock, workload_service: WorkloadService
    ) -> None:
        mock_container.get_service.side_effect = ConnectionError("socket not found")

        assert workload_service.get_service() is None

    @pytest.mark.parametrize(
        "checks",
        [ConnectionError("socket not found"), {}],
        ids=["pebble-unreachable", "check-missing"],
    )
    def test_checks_unavailable(
        self,
        mock_container: MagicMock,
        workload_service: WorkloadService,
        checks: Exception | dict,
    ) -> None:
        mock_container.get_service.return_value = MagicMock()
        mock_container.get_checks.side_effect = [checks, checks]

        assert workload_service.is_running() is False
        assert workload_service.is_failing() is False

    def test_service_that_failed_to_start_is_failing(
        self, mock_container: MagicMock, workload_service: WorkloadService
    ) -> None:
        """Older Pebble reports a service that exits right after its start as inactive."""
        mock_container.get_service.return_value = MagicMock(current=ServiceStatus.INACTIVE)
        mock_container.get_checks.return_value = {PEBBLE_READY_CHECK_NAME: MagicMock(failures=3)}

        assert workload_service.is_failing() is True

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
        mock_container.start.assert_not_called()

    @pytest.mark.parametrize(
        "service_status, started",
        [(ServiceStatus.INACTIVE, True), (ServiceStatus.ACTIVE, False), ("backoff", False)],
    )
    def test_plan_when_config_files_match(
        self,
        mock_container: MagicMock,
        pebble_service: PebbleService,
        service_status: ServiceStatus | str,
        started: bool,
    ) -> None:
        # Simulate local config file matching new config
        mock_file_cm = MagicMock()
        mock_file_cm.__enter__.return_value.read.return_value = "config_file"
        mock_container.pull.return_value = mock_file_cm
        mock_container.get_service.return_value = MagicMock(current=service_status)

        layer = {"services": {"hydra": {"override": "replace"}}}

        pebble_service.plan(layer, config_file=ConfigFile("config_file"))

        # Expect replan, NO push or restart
        mock_container.push.assert_not_called()
        mock_container.restart.assert_not_called()
        mock_container.replan.assert_called_once()
        # Replan does not start a stopped service; one that is backing off is left to Pebble
        assert mock_container.start.called is started

    def test_plan_error_leaves_out_the_service_output(
        self, mock_container: MagicMock, pebble_service: PebbleService
    ) -> None:
        """Pebble attaches what the service printed, and Hydra prints the values it rejects."""
        mock_file_cm = MagicMock()
        mock_file_cm.__enter__.return_value.read.return_value = "old_config"
        mock_container.pull.return_value = mock_file_cm
        error = ChangeError(
            "cannot start service: exited quickly with code 1",
            MagicMock(tasks=[MagicMock(log=["secrets.system.0: sh0rt-s3cr3t"])]),
        )
        mock_container.restart.side_effect = error

        with pytest.raises(PebbleServiceError) as raised:
            pebble_service.plan({"services": {}}, config_file=ConfigFile("new_config"))

        assert "exited quickly with code 1" in str(raised.value)
        assert "sh0rt-s3cr3t" not in str(raised.value)
        assert raised.value.__cause__ is error

    @pytest.mark.parametrize("failing_call", ["add_layer", "pull"])
    def test_plan_when_pebble_is_unreachable(
        self, mock_container: MagicMock, pebble_service: PebbleService, failing_call: str
    ) -> None:
        getattr(mock_container, failing_call).side_effect = ConnectionError("socket not found")

        with pytest.raises(PebbleServiceError):
            pebble_service.plan({"services": {}}, config_file=ConfigFile("config_file"))

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

    def test_stop_drops_the_alive_check_level(
        self, mock_container: MagicMock, pebble_service: PebbleService
    ) -> None:
        pebble_service.stop()

        label, layer = mock_container.add_layer.call_args.args
        assert label == WORKLOAD_SERVICE
        assert mock_container.add_layer.call_args.kwargs == {"combine": True}
        assert layer.to_dict() == {
            "checks": {
                PEBBLE_ALIVE_CHECK_NAME: {
                    "override": "replace",
                    "http": {"url": "http://localhost:4445/health/alive"},
                }
            }
        }
