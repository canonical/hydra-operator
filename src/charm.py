#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""A Juju charm for Ory Hydra."""

import json
import logging
from os.path import join
from pathlib import Path
from secrets import token_hex
from typing import Any, Dict, Optional

from charms.data_platform_libs.v0.data_interfaces import (
    DatabaseCreatedEvent,
    DatabaseEndpointsChangedEvent,
    DatabaseRequires,
)
from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
from charms.hydra.v0.hydra_endpoints import HydraEndpointsProvider
from charms.hydra.v0.oauth import (
    ClientChangedEvent,
    ClientCreatedEvent,
    ClientDeletedEvent,
    OAuthProvider,
)
from charms.identity_platform_login_ui_operator.v0.login_ui_endpoints import (
    LoginUIEndpointsRelationDataMissingError,
    LoginUIEndpointsRelationMissingError,
    LoginUIEndpointsRequirer,
    LoginUITooManyRelatedAppsError,
)
from charms.loki_k8s.v0.loki_push_api import LogProxyConsumer, PromtailDigestError
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.tempo_k8s.v0.tracing import TracingEndpointRequirer
from charms.traefik_k8s.v2.ingress import (
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
    LeaderElectedEvent,
    RelationCreatedEvent,
    RelationDepartedEvent,
    RelationEvent,
    WorkloadEvent,
)
from ops.main import main
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    MaintenanceStatus,
    ModelError,
    Relation,
    Secret,
    SecretNotFoundError,
    WaitingStatus,
)
from ops.pebble import ChangeError, Error, ExecError, Layer

from hydra_cli import HydraCLI
from utils import normalise_url, remove_none_values

logger = logging.getLogger(__name__)

EXTRA_USER_ROLES = "SUPERUSER"
HYDRA_ADMIN_PORT = 4445
HYDRA_PUBLIC_PORT = 4444
SUPPORTED_SCOPES = ["openid", "profile", "email", "phone"]
PEER = "hydra"
LOG_LEVELS = ["panic", "fatal", "error", "warn", "info", "debug", "trace"]
DB_MIGRATION_VERSION_KEY = "migration_version"
COOKIE_SECRET_KEY = "cookie"
COOKIE_SECRET_LABEL = "cookiesecret"
SYSTEM_SECRET_KEY = "system"
SYSTEM_SECRET_LABEL = "systemsecret"


class HydraCharm(CharmBase):
    """Charmed Ory Hydra."""

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)

        self._container_name = "hydra"
        self._container = self.unit.get_container(self._container_name)
        self._hydra_config_path = "/etc/config/hydra.yaml"
        self._db_name = f"{self.model.name}_{self.app.name}"
        self._db_relation_name = "pg-database"
        self._login_ui_relation_name = "ui-endpoint-info"
        self._prometheus_scrape_relation_name = "metrics-endpoint"
        self._loki_push_api_relation_name = "logging"
        self._grafana_dashboard_relation_name = "grafana-dashboard"
        self._tracing_relation_name = "tracing"
        self._hydra_service_command = "hydra serve all"
        self._log_dir = Path("/var/log")
        self._log_path = self._log_dir / "hydra.log"

        self._hydra_cli = HydraCLI(
            f"http://localhost:{HYDRA_ADMIN_PORT}", self._container, self._hydra_config_path
        )

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
            redirect_https=False,
        )
        self.public_ingress = IngressPerAppRequirer(
            self,
            relation_name="public-ingress",
            port=HYDRA_PUBLIC_PORT,
            strip_prefix=True,
            redirect_https=False,
        )
        self.oauth = OAuthProvider(self)

        self.login_ui_endpoints = LoginUIEndpointsRequirer(
            self, relation_name=self._login_ui_relation_name
        )

        self.endpoints_provider = HydraEndpointsProvider(self)

        self.metrics_endpoint = MetricsEndpointProvider(
            self,
            relation_name=self._prometheus_scrape_relation_name,
            jobs=[
                {
                    "job_name": "hydra_metrics",
                    "metrics_path": "/admin/metrics/prometheus",
                    "static_configs": [
                        {
                            "targets": [f"*:{HYDRA_ADMIN_PORT}"],
                        }
                    ],
                }
            ],
        )

        self.loki_consumer = LogProxyConsumer(
            self,
            log_files=[str(self._log_path)],
            relation_name=self._loki_push_api_relation_name,
            container_name=self._container_name,
        )

        self._grafana_dashboards = GrafanaDashboardProvider(
            self, relation_name=self._grafana_dashboard_relation_name
        )

        self.tracing = TracingEndpointRequirer(
            self,
            relation_name=self._tracing_relation_name,
        )

        self.framework.observe(self.on.hydra_pebble_ready, self._on_hydra_pebble_ready)
        self.framework.observe(self.on.leader_elected, self._on_leader_elected)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(
            self.endpoints_provider.on.ready, self._update_hydra_endpoints_relation_data
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

        self.framework.observe(self.tracing.on.endpoint_changed, self._on_config_changed)
        self.framework.observe(self.tracing.on.endpoint_removed, self._on_config_changed)

        self.framework.observe(self.on.oauth_relation_created, self._on_oauth_relation_created)
        self.framework.observe(self.oauth.on.client_created, self._on_client_created)
        self.framework.observe(self.oauth.on.client_changed, self._on_client_changed)
        self.framework.observe(self.oauth.on.client_deleted, self._on_client_deleted)

        self.framework.observe(
            self.on[self._login_ui_relation_name].relation_changed,
            self._handle_status_update_config,
        )
        self.framework.observe(
            self.on.create_oauth_client_action, self._on_create_oauth_client_action
        )
        self.framework.observe(
            self.on.get_oauth_client_info_action, self._on_get_oauth_client_info_action
        )
        self.framework.observe(
            self.on.update_oauth_client_action, self._on_update_oauth_client_action
        )
        self.framework.observe(
            self.on.delete_oauth_client_action, self._on_delete_oauth_client_action
        )
        self.framework.observe(
            self.on.list_oauth_clients_action, self._on_list_oauth_clients_action
        )
        self.framework.observe(
            self.on.revoke_oauth_client_access_tokens_action,
            self._on_revoke_oauth_client_access_tokens_action,
        )
        self.framework.observe(self.on.rotate_key_action, self._on_rotate_key_action)

        self.framework.observe(
            self.loki_consumer.on.promtail_digest_error,
            self._promtail_error,
        )

    @property
    def _hydra_service_params(self) -> str:
        ret = ["--config", str(self._hydra_config_path)]
        if self.config["dev"]:
            logger.warning("Running Hydra in dev mode, don't do this in production")
            ret.append("--dev")

        return " ".join(ret)

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
                    "command": '/bin/sh -c "{} {} 2>&1 | tee -a {}"'.format(
                        self._hydra_service_command,
                        self._hydra_service_params,
                        str(self._log_path),
                    ),
                    "startup": "disabled",
                }
            },
            "checks": {
                "ready": {
                    "override": "replace",
                    "http": {"url": f"http://localhost:{HYDRA_ADMIN_PORT}/health/ready"},
                },
            },
        }

        if self._tracing_ready:
            layer_config["services"][self._container_name]["environment"] = {
                "TRACING_PROVIDER": "otel",
                "TRACING_PROVIDERS_OTLP_SERVER_URL": self._get_tracing_endpoint_info(),
                "TRACING_PROVIDERS_OTLP_INSECURE": "true",
                "TRACING_PROVIDERS_OTLP_SAMPLING_SAMPLING_RATIO": "1.0",
            }

        return Layer(layer_config)

    @property
    def _hydra_service_is_created(self) -> bool:
        return (
            self._container.can_connect()
            and self._container_name in self._container.get_services()
        )

    @property
    def _hydra_service_is_running(self) -> bool:
        return (
            self._hydra_service_is_created
            and self._container.get_service(self._container_name).is_running
        )

    @property
    def _log_level(self) -> str:
        return self.config["log_level"]

    def _validate_config_log_level(self) -> bool:
        is_valid = self._log_level in LOG_LEVELS
        if not is_valid:
            logger.info(f"Invalid configuration value for log_level: {self._log_level}")
            self.unit.status = BlockedStatus("Invalid configuration value for log_level")
        return is_valid

    def _on_config_changed(self, event: ConfigChangedEvent) -> None:
        """Event Handler for config changed event."""
        self._handle_status_update_config(event)

    @property
    def _public_url(self) -> Optional[str]:
        url = self.public_ingress.url
        return normalise_url(url) if url else None

    @property
    def _admin_url(self) -> Optional[str]:
        url = self.admin_ingress.url
        return normalise_url(url) if url else None

    @property
    def _tracing_ready(self) -> bool:
        return self.tracing.is_ready()

    def _render_conf_file(self) -> str:
        """Render the Hydra configuration file."""
        with open("templates/hydra.yaml.j2", "r") as file:
            template = Template(file.read())

        secrets = self._get_secrets()
        rendered = template.render(
            cookie_secrets=[secrets["cookie"] if secrets else None],
            system_secrets=[secrets["system"] if secrets else None],
            log_level=self._log_level,
            db_info=self._get_database_relation_info(),
            consent_url=self._get_login_ui_endpoint_info("consent_url"),
            error_url=self._get_login_ui_endpoint_info("oidc_error_url"),
            login_url=self._get_login_ui_endpoint_info("login_url"),
            device_verification_url=self._get_login_ui_endpoint_info("device_verification_url"),
            post_device_done_url=self._get_login_ui_endpoint_info("post_device_done_url"),
            hydra_public_url=self._public_url,
            supported_scopes=SUPPORTED_SCOPES,
        )
        return rendered

    def _set_version(self) -> None:
        version = self._hydra_cli.get_version()
        self.unit.set_workload_version(version)

    def _get_database_relation_info(self) -> dict:
        if not self.database.relations:
            return None

        relation_id = self.database.relations[0].id
        relation_data = self.database.fetch_relation_data()[relation_id]

        return {
            "username": relation_data.get("username"),
            "password": relation_data.get("password"),
            # endpoints is a comma separated list, pick the first endpoint as hydra supports only one
            "endpoints": relation_data.get("endpoints").split(",")[0],
            "database_name": self._db_name,
        }

    @property
    def _dsn(self) -> Optional[str]:
        db_info = self._get_database_relation_info()
        if not db_info:
            return None

        return "postgres://{username}:{password}@{endpoints}/{database_name}".format(
            username=db_info.get("username"),
            password=db_info.get("password"),
            endpoints=db_info.get("endpoints"),
            database_name=db_info.get("database_name"),
        )

    def _run_sql_migration(self, timeout: float = 60) -> bool:
        """Runs a command to create SQL schemas and apply migration plans."""
        try:
            self._hydra_cli.run_migration(dsn=self._dsn, timeout=timeout)
        except ExecError as err:
            logger.error(f"Exited with code {err.exit_code}. Stderr: {err.stderr}")
            return False
        return True

    def _oauth_relation_peer_data_key(self, relation_id: int) -> str:
        return f"oauth_{relation_id}"

    @property
    def _migration_peer_data_key(self) -> Optional[str]:
        if not self.database.relations:
            return None
        # We append the relation ID to the migration key in peer data, this is
        # needed in order to be able to store multiple migration versions.
        #
        # When a database relation is departed, we can't remove the key because we
        # can't be sure if the relation is actually departing or if the unit is
        # dying. If a new database relation is then created we need to be able to tell
        # that it is a different relation. By appending the relation ID we overcome this
        # problem.
        # See https://github.com/canonical/hydra-operator/pull/138#discussion_r1338409081
        return f"{DB_MIGRATION_VERSION_KEY}_{self.database.relations[0].id}"

    @property
    def _peers(self) -> Optional[Relation]:
        """Fetch the peer relation."""
        return self.model.get_relation(PEER)

    def _set_peer_data(self, key: str, data: Dict) -> None:
        """Put information into the peer data bucket."""
        if not (peers := self._peers):
            return
        peers.data[self.app][key] = json.dumps(data)

    def _get_peer_data(self, key: str) -> Dict:
        """Retrieve information from the peer data bucket."""
        if not (peers := self._peers):
            return {}
        data = peers.data[self.app].get(key, "")
        return json.loads(data) if data else {}

    def _pop_peer_data(self, key: str) -> Dict:
        """Retrieve and remove information from the peer data bucket."""
        if not (peers := self._peers):
            return {}
        data = peers.data[self.app].pop(key, "")
        return json.loads(data) if data else {}

    def _set_oauth_relation_peer_data(self, relation_id: int, data: Dict) -> None:
        key = self._oauth_relation_peer_data_key(relation_id)
        self._set_peer_data(key, data)

    def _get_oauth_relation_peer_data(self, relation_id: int) -> Dict:
        key = self._oauth_relation_peer_data_key(relation_id)
        return self._get_peer_data(key)

    def _pop_oauth_relation_peer_data(self, relation_id: int) -> Dict:
        key = self._oauth_relation_peer_data_key(relation_id)
        return self._pop_peer_data(key)

    def _get_secrets(self) -> Optional[Dict[str, str]]:
        juju_secrets = {}
        try:
            juju_secret = self.model.get_secret(label=COOKIE_SECRET_LABEL)
            juju_secrets["cookie"] = juju_secret.get_content()[COOKIE_SECRET_KEY]

            juju_secret = self.model.get_secret(label=SYSTEM_SECRET_LABEL)
            juju_secrets["system"] = juju_secret.get_content()[SYSTEM_SECRET_KEY]
        except SecretNotFoundError:
            return None
        return juju_secrets

    def _create_secrets(self) -> Optional[Dict[str, Secret]]:
        if not self.unit.is_leader():
            return None

        juju_secrets = {}
        secret = {COOKIE_SECRET_KEY: token_hex(16)}
        juju_secrets["cookie"] = self.model.app.add_secret(secret, label=COOKIE_SECRET_LABEL)

        secret = {SYSTEM_SECRET_KEY: token_hex(16)}
        juju_secrets["system"] = self.model.app.add_secret(secret, label=SYSTEM_SECRET_LABEL)
        return juju_secrets

    # flake8: noqa: C901
    def _handle_status_update_config(self, event: HookEvent) -> None:
        if not self._container.can_connect():
            event.defer()
            logger.info("Cannot connect to Hydra container. Deferring the event.")
            self.unit.status = WaitingStatus("Waiting to connect to Hydra container")
            return

        if not self._validate_config_log_level():
            return

        self.unit.status = MaintenanceStatus("Configuring resources")

        if not self.model.relations[self._db_relation_name]:
            self.unit.status = BlockedStatus("Missing required relation with postgresql")
            return

        if not self.public_ingress.is_ready():
            self.unit.status = BlockedStatus("Missing required relation with ingress")
            return

        if not self.database.is_resource_created():
            self.unit.status = WaitingStatus("Waiting for database creation")
            return

        if self._migration_is_needed():
            self.unit.status = WaitingStatus(
                "Waiting for migration to run, try running the `run-migration` action"
            )
            return

        if not self._get_secrets():
            self.unit.status = WaitingStatus("Waiting for secrets creation")
            event.defer()
            return

        self._cleanup_peer_data()
        self._container.push(self._hydra_config_path, self._render_conf_file(), make_dirs=True)
        self._container.add_layer(self._container_name, self._hydra_layer, combine=True)
        try:
            self._container.restart(self._container_name)
        except ChangeError as err:
            logger.error(str(err))
            self.unit.status = BlockedStatus("Failed to restart, please consult the logs")
            return

        self.unit.status = ActiveStatus()

    def _on_leader_elected(self, event: LeaderElectedEvent) -> None:
        if not self.unit.is_leader():
            return

        if not self._get_secrets():
            self._create_secrets()

    def _update_hydra_endpoints_relation_data(self, event: RelationEvent) -> None:
        logger.info("Sending endpoints info")

        admin_endpoint = (
            self._admin_url
            or f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{HYDRA_ADMIN_PORT}"
        )
        public_endpoint = (
            self._public_url
            or f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{HYDRA_PUBLIC_PORT}"
        )

        admin_endpoint, public_endpoint = (
            admin_endpoint.replace("https", "http"),
            public_endpoint.replace("https", "http"),
        )

        self.endpoints_provider.send_endpoint_relation_data(admin_endpoint, public_endpoint)

    def _on_hydra_pebble_ready(self, event: WorkloadEvent) -> None:
        """Event Handler for pebble ready event."""
        # Necessary directory for log forwarding
        if not self._container.can_connect():
            event.defer()
            self.unit.status = WaitingStatus("Waiting to connect to Hydra container")
            return
        if not self._container.isdir(str(self._log_dir)):
            self._container.make_dir(path=str(self._log_dir), make_parents=True)
            logger.info(f"Created directory {self._log_dir}")

        self._set_version()
        self._handle_status_update_config(event)

    def _migration_is_needed(self):
        if not self._peers:
            return

        return self._get_peer_data(self._migration_peer_data_key) != self._hydra_cli.get_version()

    def _on_database_created(self, event: DatabaseCreatedEvent) -> None:
        """Event Handler for database created event."""
        logger.info("Retrieved database details")

        if not self._container.can_connect():
            event.defer()
            logger.info("Cannot connect to Hydra container. Deferring the event.")
            self.unit.status = WaitingStatus("Waiting to connect to Hydra container")
            return

        if not self._peers:
            self.unit.status = WaitingStatus("Waiting for peer relation")
            event.defer()
            return

        if not self._get_secrets():
            self.unit.status = WaitingStatus("Waiting for secret creation")
            event.defer()
            return

        if not self._migration_is_needed():
            self._handle_status_update_config(event)
            return

        if not self.unit.is_leader():
            logger.info("Unit does not have leadership")
            self.unit.status = WaitingStatus("Unit waiting for leadership to run the migration")
            event.defer()
            return

        if not self._run_sql_migration():
            self.unit.status = BlockedStatus("Database migration job failed")
            logger.error("Automigration job failed, please use the run-migration action")
            return

        self._set_peer_data(self._migration_peer_data_key, self._hydra_cli.get_version())
        self._handle_status_update_config(event)

    def _on_database_changed(self, event: DatabaseEndpointsChangedEvent) -> None:
        """Event Handler for database changed event."""
        self._handle_status_update_config(event)

    def _on_run_migration(self, event: ActionEvent) -> None:
        """Runs the migration as an action response."""
        if not self._container.can_connect():
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        timeout = float(event.params.get("timeout", 120))
        event.log("Migrating database.")
        try:
            self._hydra_cli.run_migration(timeout=timeout, dsn=self._dsn)
        except Error as e:
            err_msg = e.stderr if isinstance(e, ExecError) else e
            event.fail(f"Database migration action failed: {err_msg}")
            return
        event.log("Successfully migrated the database.")

        if not self._peers:
            event.fail("Peer relation not ready. Failed to store migration version")
            return
        self._set_peer_data(self._migration_peer_data_key, self._hydra_cli.get_version())
        event.log("Updated migration version in peer data.")

        self._handle_status_update_config(event)

    def _on_database_relation_departed(self, event: RelationDepartedEvent) -> None:
        """Event Handler for database relation departed event."""
        self.unit.status = BlockedStatus("Missing required relation with postgresql")

    def _cleanup_peer_data(self) -> None:
        if not self._peers:
            return
        # We need to remove the migration key from peer data. We can't do that in relation
        # departed as we can't tell if the event was triggered from a dying unit or if the
        # relation is actually departing.
        extra_keys = [
            k
            for k in self._peers.data[self.app].keys()
            if k.startswith(DB_MIGRATION_VERSION_KEY) and k != self._migration_peer_data_key
        ]
        for k in extra_keys:
            self._pop_peer_data(k)

    def _on_admin_ingress_ready(self, event: IngressPerAppReadyEvent) -> None:
        if self.unit.is_leader():
            logger.info("This app's admin ingress URL: %s", event.url)

        self._update_oauth_endpoint_info(event)
        self._update_hydra_endpoints_relation_data(event)

    def _on_public_ingress_ready(self, event: IngressPerAppReadyEvent) -> None:
        if self.unit.is_leader():
            logger.info("This app's public ingress URL: %s", event.url)

        self._handle_status_update_config(event)
        self._update_oauth_endpoint_info(event)
        self._update_hydra_endpoints_relation_data(event)

    def _on_ingress_revoked(self, event: IngressPerAppRevokedEvent) -> None:
        if self.unit.is_leader():
            logger.info("This app no longer has ingress")

        self._handle_status_update_config(event)
        self._update_oauth_endpoint_info(event)
        self._update_hydra_endpoints_relation_data(event)

    def _on_oauth_relation_created(self, event: RelationCreatedEvent) -> None:
        self._update_oauth_endpoint_info(event)

    def _on_client_created(self, event: ClientCreatedEvent) -> None:
        if not self.unit.is_leader():
            return

        if not self._hydra_service_is_running:
            self.unit.status = WaitingStatus("Waiting for Hydra service")
            event.defer()
            return

        if not self._peers:
            self.unit.status = WaitingStatus("Waiting for peer relation")
            event.defer()
            return

        try:
            client = self._hydra_cli.create_client(
                audience=event.audience,
                grant_type=event.grant_types,
                redirect_uri=event.redirect_uri.split(" "),
                scope=event.scope.split(" "),
                token_endpoint_auth_method=event.token_endpoint_auth_method,
                metadata={"relation_id": event.relation_id},
            )
        except ExecError as err:
            logger.error(f"Exited with code: {err.exit_code}. Stderr: {err.stderr}")
            logger.info("Deferring the event")
            event.defer()
            return

        self._set_oauth_relation_peer_data(event.relation_id, dict(client_id=client["client_id"]))
        self.oauth.set_client_credentials_in_relation_data(
            event.relation_id, client["client_id"], client["client_secret"]
        )

    def _on_client_changed(self, event: ClientChangedEvent) -> None:
        if not self.unit.is_leader():
            return

        if not self._hydra_service_is_running:
            self.unit.status = WaitingStatus("Waiting for Hydra service")
            event.defer()
            return

        try:
            self._hydra_cli.update_client(
                event.client_id,
                audience=event.audience,
                grant_type=event.grant_types,
                redirect_uri=event.redirect_uri.split(" "),
                scope=event.scope.split(" "),
                token_endpoint_auth_method=event.token_endpoint_auth_method,
                metadata={"relation_id": event.relation_id},
            )
        except ExecError as err:
            logger.error(f"Exited with code: {err.exit_code}. Stderr: {err.stderr}")
            logger.info("Deferring the event")
            event.defer()
            return

    def _on_client_deleted(self, event: ClientDeletedEvent) -> None:
        if not self.unit.is_leader():
            return

        if not self._hydra_service_is_running:
            self.unit.status = WaitingStatus("Waiting for Hydra service")
            event.defer()
            return

        if not self._peers:
            self.unit.status = WaitingStatus("Waiting for peer relation")
            event.defer()
            return

        client = self._get_oauth_relation_peer_data(event.relation_id)
        if not client:
            logger.error("No client found in peer data")
            return

        try:
            self._hydra_cli.delete_client(client["client_id"])
        except ExecError as err:
            logger.error(f"Exited with code: {err.exit_code}. Stderr: {err.stderr}")
            logger.info("Deferring the event")
            event.defer()
            return

        self._pop_oauth_relation_peer_data(event.relation_id)

    def _on_create_oauth_client_action(self, event: ActionEvent) -> None:
        if not self._hydra_service_is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        event.log("Creating client")

        cmd_kwargs = remove_none_values(
            {
                "audience": event.params.get("audience"),
                "grant_type": event.params.get("grant-types"),
                "redirect_uri": event.params.get("redirect-uris"),
                "response_type": event.params.get("response-types"),
                "scope": event.params.get("scope"),
                "client_secret": event.params.get("client-secret"),
                "token_endpoint_auth_method": event.params.get("token-endpoint-auth-method"),
            }
        )

        try:
            client = self._hydra_cli.create_client(**cmd_kwargs)
        except Error as e:
            event.fail(f"Something went wrong when trying to run the command: {e}")
            return

        event.log("Successfully created client")
        event.set_results(
            {
                "client-id": client.get("client_id"),
                "client-secret": client.get("client_secret"),
                "audience": client.get("audience"),
                "grant-types": ", ".join(client.get("grant_types", [])),
                "redirect-uris": ", ".join(client.get("redirect_uris", [])),
                "response-types": ", ".join(client.get("response_types", [])),
                "scope": client.get("scope"),
                "token-endpoint-auth-method": client.get("token_endpoint_auth_method"),
            }
        )

    def _on_get_oauth_client_info_action(self, event: ActionEvent) -> None:
        if not self._hydra_service_is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        client_id = event.params["client-id"]
        event.log(f"Getting client: {client_id}")

        try:
            client = self._hydra_cli.get_client(client_id)
        except ExecError as err:
            if err.stderr and "Unable to locate the resource" in err.stderr:
                event.fail(f"No such client: {client_id}")
                return
            event.fail(f"Exited with code: {err.exit_code}. Stderr: {err.stderr}")
            return
        except Error as e:
            event.fail(f"Something went wrong when trying to run the command: {e}")
            return

        event.log(f"Successfully fetched client: {client_id}")
        # We dump everything in the result, but we have to first convert it to the
        # format the juju action expects
        event.set_results(
            {
                k.replace("_", "-"): ", ".join(v) if isinstance(v, list) else v
                for k, v in client.items()
            }
        )

    def _on_update_oauth_client_action(self, event: ActionEvent) -> None:
        if not self._hydra_service_is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        client_id = event.params["client-id"]
        try:
            client = self._hydra_cli.get_client(client_id)
        except ExecError as err:
            if err.stderr and "Unable to locate the resource" in err.stderr:
                event.fail(f"No such client: {client_id}")
                return
            event.fail(f"Exited with code: {err.exit_code}. Stderr: {err.stderr}")
            return
        except Error as e:
            logger.error(f"Something went wrong when trying to run the command: {e}")
            return

        if self._is_oauth_relation_client(client):
            event.fail(
                f"Cannot update client `{client_id}`, it is managed from an oauth relation."
            )
            return

        cmd_kwargs = remove_none_values(
            {
                "audience": event.params.get("audience") or client.get("audience"),
                "grant_type": event.params.get("grant-types") or client.get("grant_types"),
                "redirect_uri": event.params.get("redirect-uris") or client.get("redirect_uris"),
                "response_type": event.params.get("response-types")
                or client.get("response_types"),
                "scope": event.params.get("scope") or client["scope"].split(" "),
                "client_secret": event.params.get("client-secret") or client.get("client_secret"),
                "token_endpoint_auth_method": event.params.get("token-endpoint-auth-method")
                or client.get("token_endpoint_auth_method"),
            }
        )
        event.log(f"Updating client: {client_id}")
        try:
            client = self._hydra_cli.update_client(client_id, **cmd_kwargs)
        except Error as e:
            event.fail(f"Something went wrong when trying to run the command: {e}")
            return

        event.log(f"Successfully updated client: {client_id}")
        event.set_results(
            {
                "client-id": client.get("client_id"),
                "client-secret": client.get("client_secret"),
                "audience": client.get("audience"),
                "grant-types": ", ".join(client.get("grant_types", [])),
                "redirect-uris": ", ".join(client.get("redirect_uris", [])),
                "response-types": ", ".join(client.get("response_types", [])),
                "scope": client.get("scope"),
                "token-endpoint-auth-method": client.get("token_endpoint_auth_method"),
            }
        )

    def _on_delete_oauth_client_action(self, event: ActionEvent) -> None:
        if not self._hydra_service_is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        client_id = event.params["client-id"]
        try:
            client = self._hydra_cli.get_client(client_id)
        except ExecError as err:
            if err.stderr and "Unable to locate the resource" in err.stderr:
                event.fail(f"No such client: {client_id}")
                return
            event.fail(f"Exited with code: {err.exit_code}. Stderr: {err.stderr}")
            return
        except Error as e:
            logger.error(f"Something went wrong when trying to run the command: {e}")
            return

        if self._is_oauth_relation_client(client):
            event.fail(
                f"Cannot delete client `{client_id}`, it is managed from an oauth relation. "
                "To delete it, remove the relation."
            )
            return

        event.log(f"Deleting client: {client_id}")
        try:
            self._hydra_cli.delete_client(client_id)
        except Error as e:
            event.fail(f"Something went wrong when trying to run the command: {e}")
            return

        event.log(f"Successfully deleted client: {client_id}")
        event.set_results({"client-id": client_id})

    def _on_list_oauth_clients_action(self, event: ActionEvent) -> None:
        if not self._hydra_service_is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        event.log("Fetching clients")
        try:
            clients = self._hydra_cli.list_clients()
        except Error as e:
            event.fail(f"Something went wrong when trying to run the command: {e}")
            return

        event.log("Successfully listed clients")
        event.set_results({str(i): c["client_id"] for i, c in enumerate(clients["items"])})

    def _on_revoke_oauth_client_access_tokens_action(self, event: ActionEvent) -> None:
        if not self._hydra_service_is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        client_id = event.params["client-id"]
        event.log(f"Deleting all access tokens for client: {client_id}")
        try:
            client = self._hydra_cli.delete_client_access_tokens(client_id)
        except ExecError as err:
            if err.stderr and "Unable to locate the resource" in err.stderr:
                event.fail(f"No such client: {client_id}")
                return
            event.fail(f"Exited with code: {err.exit_code}. Stderr: {err.stderr}")
            return
        except Error as e:
            event.fail(f"Something went wrong when trying to run the command: {e}")
            return

        event.log(f"Successfully deleted all access tokens for client: {client_id}")
        event.set_results({"client-id": client})

    def _on_rotate_key_action(self, event: ActionEvent) -> None:
        if not self._hydra_service_is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        event.log("Rotating keys")
        try:
            jwk = self._hydra_cli.create_jwk(alg=event.params["alg"])
        except ExecError as err:
            event.fail(f"Exited with code: {err.exit_code}. Stderr: {err.stderr}")
            return
        except Error as e:
            event.fail(f"Something went wrong when trying to run the command: {e}")
            return

        event.log("Successfully created new key")
        event.set_results({"new-key-id": jwk["keys"][0]["kid"]})

    def _is_oauth_relation_client(self, client: Dict) -> bool:
        """Check whether a client is managed from an oauth relation."""
        return "relation_id" in client.get("metadata", {})

    def _update_oauth_endpoint_info(self, event: RelationEvent) -> None:
        if not self.admin_ingress.url or not self.public_ingress.url:
            event.defer()
            logger.info("Ingress URL not available. Deferring the event.")
            return

        self.oauth.set_provider_info_in_relation_data(
            issuer_url=self._public_url,
            authorization_endpoint=join(self._public_url, "oauth2/auth"),
            token_endpoint=join(self._public_url, "oauth2/token"),
            introspection_endpoint=join(self._admin_url, "admin/oauth2/introspect"),
            userinfo_endpoint=join(self._public_url, "userinfo"),
            jwks_endpoint=join(self._public_url, ".well-known/jwks.json"),
            scope=" ".join(SUPPORTED_SCOPES),
        )

    def _get_login_ui_endpoint_info(self, key: str) -> Optional[str]:
        try:
            login_ui_endpoints = self.login_ui_endpoints.get_login_ui_endpoints()
            return login_ui_endpoints[key]
        except LoginUIEndpointsRelationDataMissingError:
            logger.info("No login ui endpoint-info relation data found")
        except LoginUIEndpointsRelationMissingError:
            logger.info("No login ui endpoint-info relation found")
        except LoginUITooManyRelatedAppsError:
            logger.info("Too many ui-endpoint-info relations found")
        return None

    def _get_tracing_endpoint_info(self) -> str:
        if not self._tracing_ready:
            return ""

        return self.tracing.otlp_http_endpoint() or ""

    def _promtail_error(self, event: PromtailDigestError) -> None:
        logger.error(event.message)


if __name__ == "__main__":
    main(HydraCharm)
