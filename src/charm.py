#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""A Juju charm for Ory Hydra."""

import glob
import logging

from charmed_kubeflow_chisme.kubernetes import KubernetesResourceHandler
from lightkube import Client
from lightkube.core.exceptions import ApiError
from lightkube.resources.apps_v1 import StatefulSet
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import ChangeError, ExecError, Layer, PathError, ProtocolError

logger = logging.getLogger(__name__)


class HydraCharm(CharmBase):
    """Charmed Ory Hydra."""

    def __init__(self, *args):
        super().__init__(*args)

        self._container_name = "hydra"
        self._container = self.unit.get_container(self._container_name)
        self._hydra_config_path = "/etc/config/hydra.yaml"
        self._name = self.model.app.name
        self._namespace = self.model.name
        self._context = {"namespace": self._namespace, "name": self._name}

        self.lightkube_client = Client(namespace=self._namespace, field_manager="lightkube")

        self.resource_handler = KubernetesResourceHandler(
            template_files=[file for file in glob.glob("src/manifests/*.yaml")],
            context=self._context,
            field_manager=self._name,
        )

        for event in [
            self.on.install,
            self.on.leader_elected,
            self.on.upgrade_charm,
            self.on.config_changed,
            self.on.hydra_pebble_ready,
        ]:
            self.framework.observe(event, self.main)

    @property
    def _hydra_layer(self) -> Layer:
        """Returns a pre-configured Pebble layer."""
        layer_config = {
            "summary": "hydra-operator layer",
            "description": "pebble config layer for hydra-operator",
            "services": {
                self._container_name: {
                    "override": "replace",
                    "summary": "entrypoint of the hydra-operator image",
                    "command": f"hydra serve all --config {self._hydra_config_path} --dangerous-force-http",
                    "startup": "enabled",
                    "environment": {
                        "DSN": self.model.config["dsn"],
                        "SECRETS_SYSTEM": self.model.config["system-secret"],
                        "SECRETS_COOKIE": self.model.config["cookie-secret"],
                    },
                }
            },
        }
        return Layer(layer_config)

    def _update_layer(self) -> None:
        """Updates the Pebble configuration layer if changed."""
        try:
            self._check_container_connection()
        except CheckFailedError as err:
            self.model.unit.status = err.status
            return

        self._push_config()

        try:
            self.resource_handler.apply()
            self.lightkube_client.patch(
                StatefulSet,
                self._name,
                {
                    "spec": {
                        "template": {
                            "spec": {
                                "containers": [
                                    {
                                        "name": "hydra",
                                        "ports": [
                                            {
                                                "name": "http-admin",
                                                "containerPort": 4445,
                                                "protocol": "TCP",
                                            },
                                            {
                                                "name": "http-public",
                                                "containerPort": 4444,
                                                "protocol": "TCP",
                                            },
                                        ],
                                    }
                                ]
                            }
                        }
                    }
                },
            )
        except ApiError as err:
            logger.error(str(err))
            self.unit.status = BlockedStatus(
                f"Applying resources failed with code {str(err.status.code)}."
            )
            return

        # Get current layer
        current_layer = self._container.get_plan()
        # Create a new config layer
        new_layer = self._hydra_layer

        if current_layer.services != new_layer.services:
            self.unit.status = MaintenanceStatus("Applying new pebble layer")
            self._container.add_layer(self._container_name, new_layer, combine=True)
            logger.info("Pebble plan updated with new configuration, replanning")
            try:
                self._container.replan()
            except ChangeError as err:
                logger.error(str(err))
                self.unit.status = BlockedStatus("Failed to replan")
                return

        self._run_sql_migration()

    def main(self, event) -> None:
        """Handles Hydra charm deployment."""
        try:
            self._check_leader()
        except CheckFailedError as err:
            self.model.unit.status = err.status
            return

        self.model.unit.status = MaintenanceStatus("Configuring hydra charm")

        self._update_layer()

        self.model.unit.status = ActiveStatus()

    def _check_leader(self) -> None:
        if not self.unit.is_leader():
            # We can't do anything useful when not the leader, so do nothing.
            raise CheckFailedError("Waiting for leadership", WaitingStatus)

    def _check_container_connection(self) -> None:
        if not self._container.can_connect():
            raise CheckFailedError("Waiting for pod startup to complete", WaitingStatus)

    def _push_config(self) -> None:
        """Pushes configuration file to Hydra container."""
        try:
            with open("src/config.yaml", encoding="utf-8") as config_file:
                config = config_file.read()
                self._container.push(self._hydra_config_path, config, make_dirs=True)
            logger.info("Pushed configs to hydra container")
        except (ProtocolError, PathError) as err:
            logger.error(str(err))
            self.unit.status = BlockedStatus(str(err))

    def _run_sql_migration(self) -> None:
        """Runs a command to create SQL schemas and apply migration plans."""
        process = self._container.exec(
            ["hydra", "migrate", "sql", "--read-from-env", "--yes"],
            environment={"DSN": self.model.config["dsn"]},
            timeout=20.0,
        )
        try:
            stdout, _ = process.wait_output()
            logger.info(f"Executing automigration: {stdout}")
        except ExecError as err:
            logger.error(f"Exited with code {err.exit_code}. Stderr: {err.stderr}")
            self.unit.status = BlockedStatus("Database migration job failed")


class CheckFailedError(Exception):
    """Raise this exception if one of the checks in main fails."""

    def __init__(self, msg, status_type=None):
        super().__init__()

        self.msg = str(msg)
        self.status_type = status_type
        self.status = status_type(self.msg)


if __name__ == "__main__":
    main(HydraCharm)
