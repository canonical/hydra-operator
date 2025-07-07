# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from ops import ModelError

from constants import (
    ADMIN_PORT,
    CONFIG_FILE_NAME,
    PUBLIC_PORT,
    WORKLOAD_CONTAINER,
    WORKLOAD_SERVICE,
)
from env_vars import DEFAULT_CONTAINER_ENV, EnvVarConvertible
from exceptions import PebbleServiceError
from services import PebbleService, WorkloadService


class TestWorkloadService:
    @pytest.fixture
    def workload_service(
        self, mocked_container: MagicMock, mocked_unit: MagicMock
    ) -> WorkloadService:
        return WorkloadService(mocked_unit)

    @pytest.mark.parametrize("version, expected", [("v1.0.0", "v1.0.0"), (None, "")])
    def test_get_version(
        self, workload_service: WorkloadService, version: Optional[str], expected: str
    ) -> None:
        with patch("cli.CommandLine.get_hydra_service_version", return_value=version):
            assert workload_service.version == expected

    def test_set_version(self, mocked_unit: MagicMock, workload_service: WorkloadService) -> None:
        workload_service.version = "v1.0.0"
        mocked_unit.set_workload_version.assert_called_once_with("v1.0.0")

    def test_set_empty_version(
        self, mocked_unit: MagicMock, workload_service: WorkloadService
    ) -> None:
        workload_service.version = ""
        mocked_unit.set_workload_version.assert_not_called()

    def test_set_version_with_error(
        self,
        mocked_unit: MagicMock,
        workload_service: WorkloadService,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        error_msg = "Error from unit"
        mocked_unit.set_workload_version.side_effect = Exception(error_msg)

        with caplog.at_level("ERROR"):
            workload_service.version = "v1.0.0"

        mocked_unit.set_workload_version.assert_called_once_with("v1.0.0")
        assert f"Failed to set workload version: {error_msg}" in caplog.text

    def test_is_running(
        self, mocked_container: MagicMock, workload_service: WorkloadService
    ) -> None:
        mocked_service_info = MagicMock(is_running=MagicMock(return_value=True))

        with patch.object(
            mocked_container, "get_service", return_value=mocked_service_info
        ) as get_service:
            is_running = workload_service.is_running

        assert is_running is True
        get_service.assert_called_once_with(WORKLOAD_CONTAINER)

    def test_is_running_with_error(
        self, mocked_container: MagicMock, workload_service: WorkloadService
    ) -> None:
        with patch.object(mocked_container, "get_service", side_effect=ModelError):
            is_running = workload_service.is_running

        assert is_running is False

    def test_open_port(self, mocked_unit: MagicMock, workload_service: WorkloadService) -> None:
        workload_service.open_port()

        assert mocked_unit.open_port.call_count == 2
        mocked_unit.open_port.assert_any_call(protocol="tcp", port=ADMIN_PORT)
        mocked_unit.open_port.assert_any_call(protocol="tcp", port=PUBLIC_PORT)


class TestPebbleService:
    @pytest.fixture
    def pebble_service(
        self, mocked_unit: MagicMock, mocked_stored_state: MagicMock
    ) -> PebbleService:
        return PebbleService(mocked_unit, mocked_stored_state)

    def test_update_config_file(
        self, mocked_container: MagicMock, pebble_service: PebbleService
    ) -> None:
        config_file_content = "config"
        changed = pebble_service.update_config_file(config_file_content)

        assert changed is True
        mocked_container.push.assert_called_once_with(
            CONFIG_FILE_NAME, config_file_content, make_dirs=True
        )

    def test_update_config_file_without_change(
        self, mocked_container: MagicMock, pebble_service: PebbleService
    ) -> None:
        config_file_content = "config"
        pebble_service.stored.config_hash = hash(config_file_content)

        changed = pebble_service.update_config_file(config_file_content)

        assert changed is False
        mocked_container.push.assert_not_called()

    @patch("ops.pebble.Layer")
    def test_plan_without_restart(
        self,
        mocked_layer: MagicMock,
        mocked_container: MagicMock,
        pebble_service: PebbleService,
    ) -> None:
        pebble_service.plan(mocked_layer, restart=False)

        mocked_container.add_layer.assert_called_once_with(
            WORKLOAD_CONTAINER, mocked_layer, combine=True
        )
        mocked_container.replan.assert_called_once()

    @patch("ops.pebble.Layer")
    def test_plan_with_restart(
        self,
        mocked_layer: MagicMock,
        mocked_container: MagicMock,
        pebble_service: PebbleService,
    ) -> None:
        pebble_service.plan(mocked_layer)

        mocked_container.add_layer.assert_called_once_with(
            WORKLOAD_CONTAINER, mocked_layer, combine=True
        )
        mocked_container.restart.assert_called_once()

    @patch("ops.pebble.Layer")
    def test_plan_failure(
        self,
        mocked_layer: MagicMock,
        mocked_container: MagicMock,
        pebble_service: PebbleService,
    ) -> None:
        with (
            patch.object(mocked_container, "restart", side_effect=Exception) as restart,
            pytest.raises(PebbleServiceError),
        ):
            pebble_service.plan(mocked_layer)

        mocked_container.add_layer.assert_called_once_with(
            WORKLOAD_CONTAINER, mocked_layer, combine=True
        )
        restart.assert_called_once()

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
