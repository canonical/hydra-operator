#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""A Juju charm for Ory Hydra."""

import glob
import logging
from base64 import b64encode

from charmed_kubeflow_chisme.kubernetes import KubernetesResourceHandler
from charmed_kubeflow_chisme.lightkube.batch import delete_many
from charms.data_platform_libs.v0.database_requires import DatabaseRequires
from lightkube import Client
from lightkube.core.exceptions import ApiError
from lightkube.resources.apps_v1 import StatefulSet
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import ChangeError, ExecError, Layer, PathError, ProtocolError

logger = logging.getLogger(__name__)

EXTRA_USER_ROLES = "SUPERUSER"


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

        database_name = f"{self.app.name.replace('-', '_')}_pg_database"
        self.pg_database = DatabaseRequires(self, "pg-database", database_name, EXTRA_USER_ROLES)

        self.lightkube_client = Client(namespace=self._namespace, field_manager="lightkube")

        self.resource_handler = KubernetesResourceHandler(
            template_files=glob.glob("src/manifests/svc.yaml"),
            context=self._context,
            field_manager=self._name,
        )

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.hydra_pebble_ready, self._on_hydra_pebble_ready)
        self.framework.observe(self.on.remove, self._on_remove)

        for db_event in [
            self.pg_database.on.database_created,
            self.pg_database.on.endpoints_changed,
        ]:
            self.framework.observe(db_event, self._on_db_events)

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
                        "SECRETS_SYSTEM": self.model.config["system-secret"],
                        "SECRETS_COOKIE": self.model.config["cookie-secret"],
                    },
                }
            },
            "checks": {
                "version": {
                    "override": "replace",
                    "exec": {"command": "hydra version"},
                },
                "ready": {
                    "override": "replace",
                    "http": {"url": "http://localhost:4445/admin/health/ready"},
                },
            },
        }
        return Layer(layer_config)

    def _check_leader(self) -> None:
        if not self.unit.is_leader():
            # We can't do anything useful when not the leader, so do nothing.
            raise CheckFailedError("Waiting for leadership", WaitingStatus)

    def _apply_and_patch_resources(self) -> None:
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
                                        "env": [
                                            {
                                                "name": "DB_USER",
                                                "valueFrom": {
                                                    "secretKeyRef": {
                                                        "name": f"{self._name}-database-secret",
                                                        "key": "username",
                                                    }
                                                },
                                            },
                                            {
                                                "name": "DB_PASSWORD",
                                                "valueFrom": {
                                                    "secretKeyRef": {
                                                        "name": f"{self._name}-database-secret",
                                                        "key": "password",
                                                    }
                                                },
                                            },
                                            {
                                                "name": "DB_ENDPOINT",
                                                "valueFrom": {
                                                    "secretKeyRef": {
                                                        "name": f"{self._name}-database-secret",
                                                        "key": "endpoint",
                                                    }
                                                },
                                            },
                                            {
                                                "name": "DSN",
                                                "value": "postgres://$(DB_USER):$(DB_PASSWORD)@$(DB_ENDPOINT)/postgres",
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
                f"Applying resources failed with code {err.status.code}."
            )
            return

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

    def _update_layer(self) -> None:
        """Updates the Pebble configuration layer if changed."""
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

    def _run_sql_migration(self) -> None:
        """Runs a command to create SQL schemas and apply migration plans."""
        process = self._container.exec(
            ["hydra", "migrate", "sql", "--read-from-env", "--yes"],
            timeout=20.0,
        )
        try:
            stdout, _ = process.wait_output()
            logger.info(f"Executing automigration: {stdout}")
        except ExecError as err:
            logger.error(f"Exited with code {err.exit_code}. Stderr: {err.stderr}")
            self.unit.status = BlockedStatus("Database migration job failed")

    def _on_install(self, _) -> None:
        """Event Handler for install event.

        - check leadership
        - check postgresql relation
        """
        try:
            self._check_leader()
        except CheckFailedError as err:
            self.model.unit.status = err.status
            return

        if not self.model.relations["pg-database"]:
            self.model.unit.status = BlockedStatus("Missing required relation for postgresql")
            return

        self.model.unit.status = MaintenanceStatus("Configuring hydra charm")

        self.model.unit.status = ActiveStatus()

    def _on_hydra_pebble_ready(self, event) -> None:
        """Event Handler for pebble ready event.

        Do the following if hydra container can be connected:
        - apply and patch k8s resources
        - push configs
        - update pebble layer
        - run sql migration
        """
        if not self.model.relations["pg-database"]:
            self.model.unit.status = BlockedStatus("Missing required relation for postgresql")
            return

        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for pod startup to complete")
            event.defer()
            return

        self.model.unit.status = MaintenanceStatus("Configuring hydra container")

        self._apply_and_patch_resources()
        self._push_config()
        self._update_layer()
        self._run_sql_migration()

        self.model.unit.status = ActiveStatus()

    def _on_remove(self, _) -> None:
        """Event Handler for remove event.

        Remove additional k8s resources created by the charm
        """
        manifests = self.resource_handler.render_manifests(force_recompute=False)
        try:
            delete_many(self.lightkube_client, manifests)
        except ApiError as e:
            logger.warning(str(e))

    def _on_db_events(self, db_event) -> None:
        """Fetch db user credentials and create a secret."""
        try:
            relation_data = self.pg_database.fetch_relation_data()
            db_data = relation_data[list(relation_data.keys())[0]]

            encoded_db_data = {
                k: b64encode(v.encode("utf-8")).decode("utf-8")
                for k, v in {
                    "username": db_data["username"],
                    "password": db_data["password"],
                    "endpoint": db_data["endpoints"],
                }.items()
            }

            secret_context = {
                "username": encoded_db_data["username"],
                "password": encoded_db_data["password"],
                "endpoint": encoded_db_data["endpoint"],
                "namespace": self._namespace,
                "name": self._name,
            }

            try:
                secret_handler = KubernetesResourceHandler(
                    template_files=glob.glob("src/manifests/secret.yaml"),
                    context=secret_context,
                    field_manager=self._name,
                )
                secret_handler.apply()
            except ApiError as err:
                logger.error(str(err))
                self.unit.status = BlockedStatus(
                    f"Applying resources failed with code {str(err.status.code)}."
                )
                return

        except Exception as e:
            logger.error(
                f"Encountered the following exception when parsing postgresql relation: {str(e)}"
            )
            raise CheckFailedError(
                "Unexpected error when parsing postgresql relation. See logs", BlockedStatus
            )
        return


class CheckFailedError(Exception):
    """Raise this exception if one of the checks in main fails."""

    def __init__(self, msg, status_type=None):
        super().__init__()

        self.msg = str(msg)
        self.status_type = status_type
        self.status = status_type(self.msg)


if __name__ == "__main__":
    main(HydraCharm)
