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
from charms.traefik_k8s.v1.ingress import (
    IngressPerAppReadyEvent,
    IngressPerAppRequirer,
    IngressPerAppRevokedEvent,
)
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import ChangeError, ExecError, Layer, PathError, ProtocolError

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
        self.admin_ingress = IngressPerAppRequirer(
            self,
            relation_name="admin-ingress",
            port=HYDRA_ADMIN_PORT,
            strip_prefix=True,
        )
        self.public_ingress = IngressPerAppRequirer(
            self,
            relation_name="public-ingress",
            port=HYDRA_PUBLIC_PORT,
            strip_prefix=True,
        )

        self.framework.observe(self.on.hydra_pebble_ready, self._on_hydra_pebble_ready)
        for db_event in [
            self.database.on.database_created,
            self.database.on.endpoints_changed,
        ]:
            self.framework.observe(db_event, self._on_db_events)

        # Admin ingress events
        self.framework.observe(self.admin_ingress.on.ready, self._on_admin_ingress_ready)
        self.framework.observe(self.admin_ingress.on.revoked, self._on_ingress_revoked)

        # Public ingress events
        self.framework.observe(self.public_ingress.on.ready, self._on_public_ingress_ready)
        self.framework.observe(self.public_ingress.on.revoked, self._on_ingress_revoked)

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
                    "startup": "enabled",
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
            "dsn": f"postgres://{db_info['username']}:{db_info['password']}@{db_info['endpoints']}/postgres",
            "log": {"level": "trace"},
            "secrets": {
                "cookie": ["my-cookie-secret"],
                "system": ["my-system-secret"],
            },
            "urls": {
                "consent": "http://localhost:3000/consent",
                "login": "http://localhost:3000/login",
                "self": {
                    "issuer": "http://localhost:4444/",
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

    def _update_layer(self) -> None:
        """Updates the Pebble configuration layer and config if changed."""
        self.unit.status = MaintenanceStatus("Applying pebble layer")

        if not self._container.get_plan().to_dict():
            # Push the config on first layer update to avoid PathError
            self._container.push(self._hydra_config_path, self._config, make_dirs=True)
            logger.info("Pushed hydra config")

        self._container.add_layer(self._container_name, self._hydra_layer, combine=True)
        logger.info("Pebble plan updated with new configuration, replanning")

        try:
            self._container.replan()
        except ChangeError as err:
            logger.error(str(err))
            self.unit.status = BlockedStatus("Failed to replan")
            return

        try:
            current_config = self._container.pull(self._hydra_config_path).read()
        except (ProtocolError, PathError) as err:
            logger.error(str(err))
            self.unit.status = BlockedStatus(str(err))
        else:
            if current_config != self._config:
                self._container.push(self._hydra_config_path, self._config, make_dirs=True)
                logger.info("Updated hydra config, restarting the container")
                self._container.restart()

    def _update_container(self, event) -> None:
        """Update configs, pebble layer and run database migration."""
        self.unit.status = MaintenanceStatus("Configuring hydra container")

        if not self.model.relations["pg-database"]:
            # TODO: Observe relation_joined event instead of event deferring
            event.defer()
            logger.error("Missing required relation with postgresql")
            self.model.unit.status = BlockedStatus("Missing required relation with postgresql")
            return

        if not self.database.is_database_created():
            event.defer()
            logger.info("Missing database details. Deferring the event.")
            self.unit.status = WaitingStatus("Waiting for database creation")
            return

        if not self._container.can_connect():
            event.defer()
            logger.info("Cannot connect to Hydra container. Deferring the event.")
            self.unit.status = WaitingStatus("Waiting to connect to Hydra container")
            return

        self._update_layer()

        if not self.unit.is_leader():
            # TODO: Observe leader_elected event
            logger.info("Unit does not have leadership")
            self.unit.status = WaitingStatus("Waiting for leadership")
            return

        self._run_sql_migration()

        self.unit.status = ActiveStatus()

    def _run_sql_migration(self) -> None:
        """Runs a command to create SQL schemas and apply migration plans."""
        process = self._container.exec(
            ["hydra", "migrate", "sql", "-e", "--config", self._hydra_config_path, "--yes"],
            timeout=20.0,
        )
        try:
            stdout, _ = process.wait_output()
            logger.info(f"Executing automigration: {stdout}")
        except ExecError as err:
            logger.error(f"Exited with code {err.exit_code}. Stderr: {err.stderr}")
            self.unit.status = BlockedStatus("Database migration job failed")

    def _on_hydra_pebble_ready(self, event) -> None:
        """Event Handler for pebble ready event."""
        self._update_container(event)

    def _on_db_events(self, db_event) -> None:
        """Event Handler for database-related events."""
        logger.info("Retrieved database details")
        self._update_container(db_event)

    def _on_admin_ingress_ready(self, event: IngressPerAppReadyEvent) -> None:
        if self.unit.is_leader():
            logger.info("This app's admin ingress URL: %s", event.url)

    def _on_public_ingress_ready(self, event: IngressPerAppReadyEvent) -> None:
        if self.unit.is_leader():
            logger.info("This app's public ingress URL: %s", event.url)

    def _on_ingress_revoked(self, event: IngressPerAppRevokedEvent) -> None:
        if self.unit.is_leader():
            logger.info("This app no longer has ingress")


if __name__ == "__main__":
    main(HydraCharm)
