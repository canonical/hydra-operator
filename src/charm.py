#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""A Juju charm for Ory Hydra."""

import logging

import yaml
from charms.data_platform_libs.v0.database_requires import DatabaseRequires
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from ops.charm import ActionEvent, CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, ModelError, WaitingStatus
from ops.pebble import ChangeError, ExecError, Layer

logger = logging.getLogger(__name__)

EXTRA_USER_ROLES = "SUPERUSER"
HYDRA_ADMIN_PORT = 4445
HYDRA_PUBLIC_PORT = 4444


class HydraCharm(CharmBase):
    """Charmed Ory Hydra."""

    def __init__(self, *args):
        super().__init__(*args)

        self._container_name = "hydra"
        self._container = self.unit.get_container(self._container_name)
        self._hydra_config_path = "/etc/config/hydra.yaml"
        self._name = self.model.app.name

        self.service_patcher = KubernetesServicePatch(
            self, [("hydra-admin", HYDRA_ADMIN_PORT), ("hydra-public", HYDRA_PUBLIC_PORT)]
        )

        self.database = DatabaseRequires(
            self,
            relation_name="pg-database",
            database_name=self._name,
            extra_user_roles=EXTRA_USER_ROLES,
        )

        self.framework.observe(self.on.hydra_pebble_ready, self._on_hydra_pebble_ready)
        self.framework.observe(self.database.on.database_created, self._on_database_created)
        self.framework.observe(self.database.on.endpoints_changed, self._on_database_changed)
        self.framework.observe(self.on.run_migration_action, self._on_run_migration)
        self.framework.observe(
            self.on["pg-database"].relation_departed, self._on_database_relation_departed
        )

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
                    "command": f"hydra serve all --config {self._hydra_config_path} --dev",
                    "startup": "disabled"
                    if not self.database.is_database_created()
                    else "enabled",
                }
            },
            "checks": {
                "version": {
                    "override": "replace",
                    "exec": {"command": "hydra version"},
                },
                "ready": {
                    "override": "replace",
                    "http": {"url": "http://localhost:4445/health/ready"},
                },
            },
        }
        return Layer(layer_config)

    @property
    def _config(self) -> str:
        """Returns Hydra configuration."""
        db_info = self._get_database_relation_info()

        config = {
            "dsn": f"postgres://{db_info['username']}:{db_info['password']}@{db_info['endpoints']}/{self._name}",
            "log": {"level": "trace"},
            "secrets": {
                "cookie": ["my-cookie-secret"],
                "system": ["my-system-secret"],
            },
            "serve": {
                "admin": {
                    "host": "localhost",
                    "port": 4445,
                },
                "public": {
                    "host": "localhost",
                    "port": 4444,
                },
            },
            "urls": {
                "consent": "http://localhost:3000/consent",
                "login": "http://localhost:3000/login",
                "self": {
                    "issuer": "http://localhost:4444/",
                    "public": "http://localhost:4444/",
                },
            },
        }

        return yaml.dump(config)

    def _get_database_relation_info(self) -> dict:
        relation_id = self.database.relations[0].id
        relation_data = self.database.fetch_relation_data()[relation_id]

        return {
            "username": relation_data["username"],
            "password": relation_data["password"],
            "endpoints": relation_data["endpoints"],
        }

    def _run_sql_migration(self) -> None:
        """Runs a command to create SQL schemas and apply migration plans."""
        process = self._container.exec(
            ["hydra", "migrate", "sql", "-e", "--config", self._hydra_config_path, "--yes"]
        )
        try:
            stdout, _ = process.wait_output()
            logger.info(f"Executing automigration: {stdout}")
        except ExecError as err:
            logger.error(f"Exited with code {err.exit_code}. Stderr: {err.stderr}")
            self.unit.status = BlockedStatus("Database migration job failed")
            logger.error("Automigration job failed, please use the run-migration action")

    def _on_hydra_pebble_ready(self, event) -> None:
        """Event Handler for pebble ready event."""
        if not self.model.relations["pg-database"]:
            # TODO: Observe relation_joined event instead of event deferring
            event.defer()
            logger.error("Missing required relation with postgresql")
            self.model.unit.status = BlockedStatus("Missing required relation with postgresql")
            return

        if not self._container.can_connect():
            event.defer()
            logger.info("Cannot connect to Hydra container. Deferring the event.")
            self.unit.status = WaitingStatus("Waiting to connect to Hydra container")
            return

        self.unit.status = MaintenanceStatus("Configuring resources")

        self._container.add_layer(self._container_name, self._hydra_layer, combine=True)
        logger.info("Pebble plan updated with new configuration, replanning")
        try:
            self._container.replan()
        except ChangeError as err:
            logger.error(str(err))
            self.unit.status = BlockedStatus("Failed to replan")
            return
        finally:
            if self.database.is_database_created():
                if not self._container.exists(self._hydra_config_path):
                    logger.info(
                        "Config file not found. Pushing it to the container and replanning"
                    )
                    self._container.push(self._hydra_config_path, self._config, make_dirs=True)
                    self._container.replan()
                self.unit.status = ActiveStatus()

    def _on_database_created(self, event) -> None:
        """Event Handler for database created event."""
        logger.info("Retrieved database details")

        if not self.unit.is_leader():
            # TODO: Observe leader_elected event
            logger.info("Unit does not have leadership")
            self.unit.status = WaitingStatus("Waiting for leadership")
            return

        if not self._container.can_connect():
            event.defer()
            logger.info("Cannot connect to Hydra container. Deferring the event.")
            self.unit.status = WaitingStatus("Waiting to connect to Hydra container")
            return

        self.unit.status = MaintenanceStatus(
            "Configuring container and resources for database connection"
        )

        try:
            self._container.add_layer(self._container_name, self._hydra_layer, combine=True)
            self._container.get_service(self._container_name)
            logger.info("Updating Hydra config and restarting service")
            self._container.push(self._hydra_config_path, self._config, make_dirs=True)
            self._run_sql_migration()
            self._container.restart(self._container_name)
            self.unit.status = ActiveStatus()
        except (ModelError, RuntimeError):
            event.defer()
            self.unit.status = WaitingStatus("Waiting for Hydra service")
            logger.info("Hydra service is absent. Deferring database created event.")

    def _on_database_changed(self, event) -> None:
        """Event Handler for database changed event."""
        if not self._container.can_connect():
            event.defer()
            logger.info("Cannot connect to Hydra container. Deferring the event.")
            self.unit.status = WaitingStatus("Waiting to connect to Hydra container")
            return

        self.unit.status = MaintenanceStatus("Updating database details")

        try:
            self._container.get_service(self._container_name)
            logger.info("Updating Hydra config and restarting service")
            self._container.push(self._hydra_config_path, self._config, make_dirs=True)
            self._container.restart(self._container_name)
            self.unit.status = ActiveStatus()
        except (ModelError, RuntimeError):
            event.defer()
            self.unit.status = WaitingStatus("Waiting for Hydra service")
            logger.info("Hydra service is absent. Deferring database created event.")

    def _on_run_migration(self, event: ActionEvent) -> None:
        """Runs the migration as an action response."""
        logger.info("Executing database migration initiated by user")
        self._run_sql_migration()

    def _on_database_relation_departed(self, event) -> None:
        """Event Handler for database relation departed event."""
        logger.error("Missing required relation with postgresql")
        self.model.unit.status = BlockedStatus("Missing required relation with postgresql")


if __name__ == "__main__":
    main(HydraCharm)
