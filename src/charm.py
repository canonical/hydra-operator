#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""A Juju charm for Ory Hydra."""

import logging
from os.path import join

from charms.data_platform_libs.v0.data_interfaces import (
    DatabaseCreatedEvent,
    DatabaseEndpointsChangedEvent,
    DatabaseRequires,
)
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from charms.traefik_k8s.v1.ingress import (
    IngressPerAppReadyEvent,
    IngressPerAppRequirer,
    IngressPerAppRevokedEvent,
)
from jinja2 import Template
from ops.charm import (
    ActionEvent,
    CharmBase,
    ConfigChangedEvent,
    HookEvent,
    RelationDepartedEvent,
    RelationEvent,
    WorkloadEvent,
)
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, ModelError, WaitingStatus
from ops.pebble import ChangeError, ExecError, Layer

from hydra_endpoints_provider import RELATION_NAME, HydraEndpointsProvider

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
        self._db_name = f"{self.model.name}_{self.app.name}"
        self._db_relation_name = "pg-database"

        self.service_patcher = KubernetesServicePatch(
            self, [("hydra-admin", HYDRA_ADMIN_PORT), ("hydra-public", HYDRA_PUBLIC_PORT)]
        )

        self.database = DatabaseRequires(
            self,
            relation_name=self._db_relation_name,
            database_name=self._db_name,
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

        self.endpoints_provider = HydraEndpointsProvider(self)

        self.framework.observe(self.on.hydra_pebble_ready, self._on_hydra_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(
            self.on[RELATION_NAME].relation_created, self._on_hydra_relation_changed
        )
        self.framework.observe(
            self.on[RELATION_NAME].relation_changed, self._on_hydra_relation_changed
        )
        self.framework.observe(self.database.on.database_created, self._on_database_created)
        self.framework.observe(self.database.on.endpoints_changed, self._on_database_changed)
        self.framework.observe(self.on.run_migration_action, self._on_run_migration)
        self.framework.observe(
            self.on[self._db_relation_name].relation_departed, self._on_database_relation_departed
        )

        self.framework.observe(self.admin_ingress.on.ready, self._on_admin_ingress_ready)
        self.framework.observe(self.admin_ingress.on.revoked, self._on_ingress_revoked)

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
                    "startup": "disabled",
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

    def _render_conf_file(self) -> None:
        """Render the Hydra configuration file."""
        with open("templates/hydra.yaml.j2", "r") as file:
            template = Template(file.read())

        rendered = template.render(
            db_info=self._get_database_relation_info(),
            consent_url=join(self.config.get("login_ui_url"), "consent"),
            error_url=join(self.config.get("login_ui_url"), "error"),
            login_url=join(self.config.get("login_ui_url"), "login"),
            hydra_public_url=self.public_ingress.url
            if self.model.relations["public-ingress"]
            else "http://127.0.0.1:4444/",
        )
        return rendered

    def _get_database_relation_info(self) -> dict:
        relation_id = self.database.relations[0].id
        relation_data = self.database.fetch_relation_data()[relation_id]

        return {
            "username": relation_data.get("username"),
            "password": relation_data.get("password"),
            "endpoints": relation_data.get("endpoints"),
            "database_name": self._db_name,
        }

    def _run_sql_migration(self, set_timeout: bool) -> None:
        """Runs a command to create SQL schemas and apply migration plans."""
        process = self._container.exec(
            ["hydra", "migrate", "sql", "-e", "--config", self._hydra_config_path, "--yes"],
            timeout=20.0 if set_timeout else None,
        )

        stdout, _ = process.wait_output()
        logger.info(f"Executing automigration: {stdout}")

    def _update_config_restart_service(self, event: HookEvent) -> None:
        if not self._container.can_connect():
            event.defer()
            logger.info("Cannot connect to Hydra container. Deferring the event.")
            self.unit.status = WaitingStatus("Waiting to connect to Hydra container")
            return

        self.unit.status = MaintenanceStatus("Configuring resources")

        try:
            self._container.get_service(self._container_name)
        except (ModelError, RuntimeError):
            event.defer()
            self.unit.status = WaitingStatus("Waiting for Hydra service")
            logger.info("Hydra service is absent. Deferring the event.")
            return

        if self.database.is_resource_created():
            self._container.push(self._hydra_config_path, self._render_conf_file(), make_dirs=True)
            self._container.start(self._container_name)
            self.unit.status = ActiveStatus()
            return

        if self.model.relations[self._db_relation_name]:
            self.unit.status = WaitingStatus("Waiting for database creation")
        else:
            self.unit.status = BlockedStatus("Missing required relation with postgresql")

    def _send_relation_info(self) -> None:
        admin_endpoint = (
            self.admin_ingress.url
            if self.model.relations["admin-ingress"]
            else "http://127.0.0.1:4445/",
        )
        public_endpoint = (
            self.public_ingress.url
            if self.model.relations["public-ingress"]
            else "http://127.0.0.1:4444/",
        )
        self.endpoints_provider.send_endpoint_relation_data(
            self.app, admin_endpoint[0], public_endpoint[0]
        )

        logger.info(
            f"Sent endpoints info: public - {public_endpoint[0]} admin - {admin_endpoint[0]}"
        )

    def _on_hydra_pebble_ready(self, event: WorkloadEvent) -> None:
        """Event Handler for pebble ready event."""
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
            self.unit.status = BlockedStatus("Failed to replan, please consult the logs")
            return

        if self.database.is_resource_created():
            self._container.push(self._hydra_config_path, self._render_conf_file(), make_dirs=True)
            self._container.start(self._container_name)
            self.unit.status = ActiveStatus()
            return

        if self.model.relations[self._db_relation_name]:
            self.unit.status = WaitingStatus("Waiting for database creation")
        else:
            self.unit.status = BlockedStatus("Missing required relation with postgresql")

    def _on_config_changed(self, event: ConfigChangedEvent) -> None:
        """Event Handler for config changed event."""
        self._update_config_restart_service(event)

    def _on_hydra_relation_changed(self, event: RelationEvent) -> None:
        """Event Handler for relation changed event."""
        self._send_relation_info()

    def _on_database_created(self, event: DatabaseCreatedEvent) -> None:
        """Event Handler for database created event."""
        logger.info("Retrieved database details")

        if not self.unit.is_leader():
            # TODO: Observe leader_elected event
            logger.info("Unit does not have leadership")
            self.unit.status = WaitingStatus("Unit waiting for leadership to run the migration")
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
            self._container.get_service(self._container_name)
        except (ModelError, RuntimeError):
            event.defer()
            self.unit.status = WaitingStatus("Waiting for Hydra service")
            logger.info("Hydra service is absent. Deferring database created event.")
            return

        logger.info("Updating Hydra config and restarting service")
        self._container.push(self._hydra_config_path, self._render_conf_file(), make_dirs=True)

        try:
            self._run_sql_migration(set_timeout=True)
        except ExecError as err:
            logger.error(f"Exited with code {err.exit_code}. Stderr: {err.stderr}")
            self.unit.status = BlockedStatus("Database migration job failed")
            logger.error("Automigration job failed, please use the run-migration action")
            return

        self._container.start(self._container_name)
        self.unit.status = ActiveStatus()

    def _on_database_changed(self, event: DatabaseEndpointsChangedEvent) -> None:
        """Event Handler for database changed event."""
        self._update_config_restart_service(event)

    def _on_run_migration(self, event: ActionEvent) -> None:
        """Runs the migration as an action response."""
        logger.info("Executing database migration initiated by user")
        try:
            self._run_sql_migration(set_timeout=False)
        except ExecError as err:
            logger.error(f"Exited with code {err.exit_code}. Stderr: {err.stderr}")
            event.fail("Execution failed, please inspect the logs")
            return

    def _on_database_relation_departed(self, event: RelationDepartedEvent) -> None:
        """Event Handler for database relation departed event."""
        logger.error("Missing required relation with postgresql")
        self.model.unit.status = BlockedStatus("Missing required relation with postgresql")
        if self._container.can_connect():
            self._container.stop(self._container_name)

    def _on_admin_ingress_ready(self, event: IngressPerAppReadyEvent) -> None:
        if self.unit.is_leader():
            logger.info("This app's admin ingress URL: %s", event.url)

        self._send_relation_info()

    def _on_public_ingress_ready(self, event: IngressPerAppReadyEvent) -> None:
        if self.unit.is_leader():
            logger.info("This app's public ingress URL: %s", event.url)

        self._update_config_restart_service(event)

    def _on_ingress_revoked(self, event: IngressPerAppRevokedEvent) -> None:
        if self.unit.is_leader():
            logger.info("This app no longer has ingress")

        self._update_config_restart_service(event)
        self._send_relation_info()


if __name__ == "__main__":
    main(HydraCharm)
