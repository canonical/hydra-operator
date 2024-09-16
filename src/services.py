# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from collections import ChainMap
from pathlib import PurePath

from ops.model import Container, ModelError, Unit
from ops.pebble import Layer, LayerDict

from cli import CommandLine
from constants import (
    ADMIN_PORT,
    CONFIG_FILE_NAME,
    HYDRA_SERVICE_COMMAND,
    LOG_FILE,
    PUBLIC_PORT,
    WORKLOAD_CONTAINER,
    WORKLOAD_SERVICE,
)
from env_vars import DEFAULT_CONTAINER_ENV, EnvVarConvertible
from exceptions import PebbleServiceError

logger = logging.getLogger(__name__)

PEBBLE_LAYER_DICT = {
    "summary": "hydra-operator layer",
    "description": "pebble config layer for hydra-operator",
    "services": {
        WORKLOAD_CONTAINER: {
            "override": "replace",
            "summary": "entrypoint of the hydra-operator image",
            "command": '/bin/sh -c "{} {} 2>&1 | tee -a {}"'.format(
                HYDRA_SERVICE_COMMAND,
                f"--config {CONFIG_FILE_NAME}",
                str(LOG_FILE),
            ),
            "startup": "disabled",
        }
    },
    "checks": {
        "ready": {
            "override": "replace",
            "http": {"url": f"http://localhost:{ADMIN_PORT}/health/ready"},
        },
    },
}


class WorkloadService:
    """Workload service abstraction running in a Juju unit."""

    def __init__(self, unit: Unit) -> None:
        self._version = ""

        self._unit: Unit = unit
        self._container: Container = unit.get_container(WORKLOAD_CONTAINER)
        self._cli = CommandLine(self._container)

    @property
    def version(self) -> str:
        self._version = self._cli.get_hydra_service_version() or ""
        return self._version

    @version.setter
    def version(self, version: str) -> None:
        if not version:
            return

        try:
            self._unit.set_workload_version(version)
        except Exception as e:
            logger.error("Failed to set workload version: %s", e)
            return
        else:
            self._version = version

    @property
    def is_running(self) -> bool:
        try:
            workload_service = self._container.get_service(WORKLOAD_CONTAINER)
        except ModelError:
            return False

        return workload_service.is_running()

    def open_port(self) -> None:
        self._unit.open_port(protocol="tcp", port=ADMIN_PORT)
        self._unit.open_port(protocol="tcp", port=PUBLIC_PORT)


class PebbleService:
    """Pebble service abstraction running in a Juju unit."""

    def __init__(self, unit: Unit) -> None:
        self._unit = unit
        self._container = unit.get_container(WORKLOAD_SERVICE)
        self._layer_dict: LayerDict = PEBBLE_LAYER_DICT

    def prepare_dir(self, path: str | PurePath) -> None:
        if self._container.isdir(path):
            return

        self._container.make_dir(path=path, make_parents=True)

    def push_config_file(self, content: str) -> None:
        self._container.push(CONFIG_FILE_NAME, content, make_dirs=True)

    def plan(self, layer: Layer) -> None:
        self._container.add_layer(WORKLOAD_CONTAINER, layer, combine=True)

        try:
            self._container.restart(WORKLOAD_CONTAINER)
        except Exception as e:
            raise PebbleServiceError(f"Pebble failed to restart the workload service. Error: {e}")

    def render_pebble_layer(self, *env_var_sources: EnvVarConvertible) -> Layer:
        updated_env_vars = ChainMap(*(source.to_env_vars() for source in env_var_sources))  # type: ignore
        env_vars = {
            **DEFAULT_CONTAINER_ENV,
            **updated_env_vars,
        }
        self._layer_dict["services"][WORKLOAD_SERVICE]["environment"] = env_vars

        return Layer(self._layer_dict)