#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

# Learn more at: https://juju.is/docs/sdk

"""A Juju charm for Ory Hydra."""

import logging
from secrets import token_hex
from typing import Any

from charms.data_platform_libs.v0.data_interfaces import (
    DatabaseCreatedEvent,
    DatabaseEndpointsChangedEvent,
    DatabaseRequires,
)
from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
from charms.hydra.v0.hydra_endpoints import HydraEndpointsProvider
from charms.hydra.v0.hydra_token_hook import HydraHookRequirer
from charms.hydra.v0.oauth import ClientChangedEvent, ClientCreatedEvent, OAuthProvider
from charms.identity_platform_login_ui_operator.v0.login_ui_endpoints import (
    LoginUIEndpointsRequirer,
)
from charms.loki_k8s.v1.loki_push_api import LogForwarder
from charms.observability_libs.v0.kubernetes_compute_resources_patch import (
    K8sResourcePatchFailedEvent,
    KubernetesComputeResourcesPatch,
    ResourceRequirements,
    adjust_resource_requirements,
)
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.tempo_coordinator_k8s.v0.tracing import TracingEndpointRequirer
from charms.traefik_k8s.v0.traefik_route import TraefikRouteRequirer
from charms.traefik_k8s.v2.ingress import (
    IngressPerAppReadyEvent,
    IngressPerAppRequirer,
    IngressPerAppRevokedEvent,
)
from ops import StoredState
from ops.charm import (
    ActionEvent,
    CharmBase,
    ConfigChangedEvent,
    HookEvent,
    LeaderElectedEvent,
    RelationBrokenEvent,
    RelationEvent,
    RelationJoinedEvent,
    WorkloadEvent,
)
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import Layer

from cli import CommandLine, OAuthClient
from configs import CharmConfig, ConfigFile
from constants import (
    ADMIN_INGRESS_INTEGRATION_NAME,
    ADMIN_PORT,
    COOKIE_SECRET_KEY,
    COOKIE_SECRET_LABEL,
    DATABASE_INTEGRATION_NAME,
    DEFAULT_OAUTH_SCOPES,
    GRAFANA_DASHBOARD_INTEGRATION_NAME,
    HYDRA_TOKEN_HOOK_INTEGRATION_NAME,
    INTERNAL_INGRESS_INTEGRATION_NAME,
    LOGGING_RELATION_NAME,
    LOGIN_UI_INTEGRATION_NAME,
    OAUTH_INTEGRATION_NAME,
    PEER_INTEGRATION_NAME,
    PROMETHEUS_SCRAPE_INTEGRATION_NAME,
    PUBLIC_INGRESS_INTEGRATION_NAME,
    PUBLIC_PORT,
    SYSTEM_SECRET_KEY,
    SYSTEM_SECRET_LABEL,
    TEMPO_TRACING_INTEGRATION_NAME,
    WORKLOAD_CONTAINER,
)
from exceptions import (
    ClientDoesNotExistError,
    CommandExecError,
    MigrationError,
    PebbleServiceError,
)
from integrations import (
    DatabaseConfig,
    HydraHookData,
    InternalIngressData,
    LoginUIEndpointData,
    PeerData,
    PublicIngressData,
    TracingData,
)
from secret import Secrets
from services import PebbleService, WorkloadService
from utils import (
    container_connectivity,
    database_integration_exists,
    leader_unit,
    login_ui_integration_exists,
    peer_integration_exists,
    public_ingress_integration_exists,
)

logger = logging.getLogger(__name__)


class HydraCharm(CharmBase):
    _stored = StoredState()

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)

        self.peer_data = PeerData(self.model)
        self.secrets = Secrets(self.model)
        self.charm_config = CharmConfig(self.config)

        self._container = self.unit.get_container(WORKLOAD_CONTAINER)
        self._workload_service = WorkloadService(self.unit)
        self._pebble_service = PebbleService(self.unit, self._stored)
        self._cli = CommandLine(self._container)

        self.token_hook = HydraHookRequirer(
            self,
            relation_name=HYDRA_TOKEN_HOOK_INTEGRATION_NAME,
        )

        self.database_requirer = DatabaseRequires(
            self,
            relation_name=DATABASE_INTEGRATION_NAME,
            database_name=f"{self.model.name}_{self.app.name}",
            extra_user_roles="SUPERUSER",
        )

        self.admin_ingress = IngressPerAppRequirer(
            self,
            relation_name=ADMIN_INGRESS_INTEGRATION_NAME,
            port=ADMIN_PORT,
            strip_prefix=True,
            redirect_https=False,
        )
        self.public_ingress = IngressPerAppRequirer(
            self,
            relation_name=PUBLIC_INGRESS_INTEGRATION_NAME,
            port=PUBLIC_PORT,
            strip_prefix=True,
            redirect_https=False,
        )

        # ingress via raw traefik routing configuration
        self.internal_ingress = TraefikRouteRequirer(
            self,
            self.model.get_relation(INTERNAL_INGRESS_INTEGRATION_NAME),
            INTERNAL_INGRESS_INTEGRATION_NAME,
        )

        self.oauth_provider = OAuthProvider(self)

        self.login_ui_requirer = LoginUIEndpointsRequirer(
            self, relation_name=LOGIN_UI_INTEGRATION_NAME
        )

        self.hydra_endpoints_provider = HydraEndpointsProvider(self)

        self.metrics_endpoint = MetricsEndpointProvider(
            self,
            relation_name=PROMETHEUS_SCRAPE_INTEGRATION_NAME,
            jobs=[
                {
                    "job_name": "hydra_metrics",
                    "metrics_path": "/admin/metrics/prometheus",
                    "static_configs": [
                        {
                            "targets": [f"*:{ADMIN_PORT}"],
                        }
                    ],
                }
            ],
        )

        self.resources_patch = KubernetesComputeResourcesPatch(
            self,
            WORKLOAD_CONTAINER,
            resource_reqs_func=self._resource_reqs_from_config,
        )

        # Loki logging relation
        self._log_forwarder = LogForwarder(self, relation_name=LOGGING_RELATION_NAME)

        self._grafana_dashboards = GrafanaDashboardProvider(
            self,
            relation_name=GRAFANA_DASHBOARD_INTEGRATION_NAME,
        )

        self.tracing_requirer = TracingEndpointRequirer(
            self, relation_name=TEMPO_TRACING_INTEGRATION_NAME, protocols=["otlp_http"]
        )

        self.framework.observe(self.on.hydra_pebble_ready, self._on_hydra_pebble_ready)
        self.framework.observe(self.on.update_status, self._holistic_handler)
        self.framework.observe(self.on.leader_elected, self._on_leader_elected)
        self.framework.observe(self.on.config_changed, self._on_config_changed)

        # hooks
        self.framework.observe(self.token_hook.on.ready, self._holistic_handler)
        self.framework.observe(self.token_hook.on.unavailable, self._holistic_handler)

        # database
        self.framework.observe(
            self.database_requirer.on.database_created, self._on_database_created
        )
        self.framework.observe(
            self.database_requirer.on.endpoints_changed, self._on_database_changed
        )
        self.framework.observe(
            self.on[DATABASE_INTEGRATION_NAME].relation_broken,
            self._on_database_integration_broken,
        )

        # admin ingress
        self.framework.observe(self.admin_ingress.on.ready, self._on_admin_ingress_ready)
        self.framework.observe(self.admin_ingress.on.revoked, self._on_ingress_revoked)

        # public ingress
        self.framework.observe(self.public_ingress.on.ready, self._on_public_ingress_ready)
        self.framework.observe(self.public_ingress.on.revoked, self._on_ingress_revoked)

        # internal ingress
        self.framework.observe(
            self.on[INTERNAL_INGRESS_INTEGRATION_NAME].relation_joined,
            self._on_internal_ingress_joined,
        )
        self.framework.observe(
            self.on[INTERNAL_INGRESS_INTEGRATION_NAME].relation_changed,
            self._on_internal_ingress_changed,
        )
        self.framework.observe(
            self.on[INTERNAL_INGRESS_INTEGRATION_NAME].relation_broken,
            self._on_internal_ingress_changed,
        )

        # login-ui
        self.framework.observe(
            self.on[LOGIN_UI_INTEGRATION_NAME].relation_changed,
            self._holistic_handler,
        )
        self.framework.observe(
            self.on[LOGIN_UI_INTEGRATION_NAME].relation_broken,
            self._holistic_handler,
        )

        # hydra-endpoints
        self.framework.observe(
            self.hydra_endpoints_provider.on.ready, self._on_hydra_endpoints_ready
        )

        # oauth
        self.framework.observe(self.on.oauth_relation_created, self._on_oauth_integration_created)
        self.framework.observe(
            self.oauth_provider.on.client_created, self._on_oauth_client_created
        )
        self.framework.observe(
            self.oauth_provider.on.client_changed, self._on_oauth_client_changed
        )
        # self.framework.observe(
        #     self.oauth_provider.on.client_deleted, self._on_oauth_client_deleted
        # )

        # tracing
        self.framework.observe(self.tracing_requirer.on.endpoint_changed, self._on_config_changed)
        self.framework.observe(self.tracing_requirer.on.endpoint_removed, self._on_config_changed)

        # resource patching
        self.framework.observe(
            self.resources_patch.on.patch_failed, self._on_resource_patch_failed
        )

        # actions
        self.framework.observe(self.on.run_migration_action, self._on_run_migration)
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
            self.on.reconcile_oauth_clients_action, self._reconcile_oauth_clients_action
        )

    @property
    def _pebble_layer(self) -> Layer:
        tracing_data = TracingData.load(self.tracing_requirer)
        return self._pebble_service.render_pebble_layer(
            self.charm_config,
            tracing_data,
        )

    @property
    def migration_needed(self) -> bool:
        if not peer_integration_exists(self):
            return False

        database_config = DatabaseConfig.load(self.database_requirer)
        return self.peer_data[database_config.migration_version] != self._workload_service.version

    @property
    def dev_mode(self) -> bool:
        return self.charm_config["dev"]

    def _on_hydra_pebble_ready(self, event: WorkloadEvent) -> None:
        self.unit.status = MaintenanceStatus("Configuring resources")
        if not container_connectivity(self):
            event.defer()
            self.unit.status = WaitingStatus("Container is not connected yet")
            return

        self._workload_service.open_port()

        service_version = self._workload_service.version
        self._workload_service.version = service_version

        self._holistic_handler(event)

    def _on_leader_elected(self, event: LeaderElectedEvent) -> None:
        if not self.secrets.is_ready:
            self.secrets[COOKIE_SECRET_LABEL] = {COOKIE_SECRET_KEY: token_hex(16)}
            self.secrets[SYSTEM_SECRET_LABEL] = {SYSTEM_SECRET_KEY: token_hex(16)}

    def _on_config_changed(self, event: ConfigChangedEvent) -> None:
        self.unit.status = MaintenanceStatus("Configuring resources")
        self._holistic_handler(event)
        self._on_oauth_integration_created(event)

    def _on_public_ingress_ready(self, event: IngressPerAppReadyEvent) -> None:
        self.unit.status = MaintenanceStatus("Configuring resources")
        self._holistic_handler(event)
        self._on_oauth_integration_created(event)
        self._on_hydra_endpoints_ready(event)

    def _on_admin_ingress_ready(self, event: IngressPerAppReadyEvent) -> None:
        self.unit.status = MaintenanceStatus("Configuring resources")
        self._on_hydra_endpoints_ready(event)

    def _on_ingress_revoked(self, event: IngressPerAppRevokedEvent) -> None:
        self.unit.status = MaintenanceStatus("Configuring resources")
        self._holistic_handler(event)
        self._on_oauth_integration_created(event)
        self._on_hydra_endpoints_ready(event)

    @leader_unit
    def _on_internal_ingress_joined(self, event: RelationJoinedEvent) -> None:
        self.unit.status = MaintenanceStatus("Configuring resources")
        self.internal_ingress._relation = event.relation
        self._on_internal_ingress_changed(event)

    @leader_unit
    def _on_internal_ingress_changed(self, event: RelationEvent) -> None:
        self.unit.status = MaintenanceStatus("Configuring resources")
        if self.internal_ingress.is_ready():
            internal_ingress_config = InternalIngressData.load(self.internal_ingress).config
            self.internal_ingress.submit_to_traefik(internal_ingress_config)
            self._on_hydra_endpoints_ready(event)
            self._on_oauth_integration_created(event)

    def _resource_reqs_from_config(self) -> ResourceRequirements:
        limits = {"cpu": self.model.config.get("cpu"), "memory": self.model.config.get("memory")}
        requests = {"cpu": "100m", "memory": "200Mi"}
        return adjust_resource_requirements(limits, requests, adhere_to_requests=True)

    def _on_database_created(self, event: DatabaseCreatedEvent) -> None:
        self.unit.status = MaintenanceStatus("Configuring resources")
        if not container_connectivity(self):
            self.unit.status = WaitingStatus("Container is not connected yet")
            event.defer()
            return

        if not peer_integration_exists(self):
            self.unit.status = WaitingStatus(f"Missing integration {PEER_INTEGRATION_NAME}")
            event.defer()
            return

        if not self.secrets.is_ready:
            self.unit.status = WaitingStatus("Missing required secrets")
            event.defer()
            return

        if not self.migration_needed:
            self._holistic_handler(event)
            return

        if not self.unit.is_leader():
            logger.info(
                "Unit does not have leadership. Wait for leader unit to run the migration."
            )
            self.unit.status = WaitingStatus("Waiting for leader unit to run the migration")
            event.defer()
            return

        try:
            self._cli.migrate(DatabaseConfig.load(self.database_requirer).dsn)
        except MigrationError:
            self.unit.status = BlockedStatus("Database migration failed")
            logger.error("Auto migration job failed. Please use the run-migration action")
            return

        migration_version = DatabaseConfig.load(self.database_requirer).migration_version
        self.peer_data[migration_version] = self._workload_service.version
        self._holistic_handler(event)

    def _on_database_changed(self, event: DatabaseEndpointsChangedEvent) -> None:
        self.unit.status = MaintenanceStatus("Configuring resources")
        self._holistic_handler(event)

    def _on_database_integration_broken(self, event: RelationBrokenEvent) -> None:
        self.unit.status = MaintenanceStatus("Configuring resources")
        self._holistic_handler(event)

    def _on_oauth_integration_created(self, event: RelationEvent) -> None:
        if not (public_url := PublicIngressData.load(self.public_ingress).url):
            event.defer()
            logger.info("Public ingress URL is not available. Deferring the event.")
            return

        internal_endpoints = InternalIngressData.load(self.internal_ingress)
        self.oauth_provider.set_provider_info_in_relation_data(
            issuer_url=str(public_url),
            authorization_endpoint=str(public_url / "oauth2/auth"),
            token_endpoint=str(public_url / "oauth2/token"),
            introspection_endpoint=str(
                internal_endpoints.admin_endpoint / "admin/oauth2/introspect"
            ),
            userinfo_endpoint=str(public_url / "userinfo"),
            jwks_endpoint=str(public_url / ".well-known/jwks.json"),
            scope=" ".join(DEFAULT_OAUTH_SCOPES),
            jwt_access_token=self.config.get("jwt_access_tokens", True),
        )

    @leader_unit
    def _on_oauth_client_created(self, event: ClientCreatedEvent) -> None:
        if not self._workload_service.is_running:
            self.unit.status = WaitingStatus("Waiting for Hydra service")
            event.defer()
            return

        if not peer_integration_exists(self):
            self.unit.status = WaitingStatus(f"Missing integration {PEER_INTEGRATION_NAME}")
            event.defer()
            return

        if self.peer_data[f"oauth_{event.relation_id}"]:
            logger.info("Got client_created event, but client already exists. Ignoring event")
            return

        target_oauth_client = OAuthClient(
            **event.snapshot(),
            **{"metadata": {"integration-id": str(event.relation_id)}},
        )
        if not (oauth_client := self._cli.create_oauth_client(target_oauth_client)):
            logger.error("Failed to create the OAuth client bound with the oauth integration")
            event.defer()
            return

        self.peer_data[f"oauth_{event.relation_id}"] = {"client_id": oauth_client.client_id}
        self.oauth_provider.set_client_credentials_in_relation_data(
            event.relation_id,
            oauth_client.client_id,  # type: ignore[arg-type]
            oauth_client.client_secret,  # type: ignore[arg-type]
        )

    @leader_unit
    def _on_oauth_client_changed(self, event: ClientChangedEvent) -> None:
        if not self._workload_service.is_running:
            self.unit.status = WaitingStatus("Waiting for Hydra service")
            event.defer()
            return

        target_oauth_client = OAuthClient(
            **event.snapshot(),
            **{"metadata": {"integration-id": str(event.relation_id)}},
        )
        if not self._cli.update_oauth_client(target_oauth_client):
            logger.error(
                "Failed to update the OAuth client bound with the oauth integration: %d",
                event.relation_id,
            )
            event.defer()

    def _on_hydra_endpoints_ready(self, event: RelationEvent) -> None:
        internal_endpoints = InternalIngressData.load(self.internal_ingress)
        self.hydra_endpoints_provider.send_endpoint_relation_data(
            str(internal_endpoints.admin_endpoint),
            str(internal_endpoints.public_endpoint),
        )

    def _on_resource_patch_failed(self, event: K8sResourcePatchFailedEvent) -> None:
        logger.error(f"Failed to patch resource constraints: {event.message}")
        self.unit.status = BlockedStatus(event.message)

    def _holistic_handler(self, event: HookEvent) -> None:  # noqa: C901
        if not container_connectivity(self):
            event.defer()
            self.unit.status = WaitingStatus("Container is not connected yet")
            return

        if not peer_integration_exists(self):
            self.unit.status = WaitingStatus(f"Missing integration {PEER_INTEGRATION_NAME}")
            event.defer()
            return

        if not database_integration_exists(self):
            self.unit.status = BlockedStatus(f"Missing integration {DATABASE_INTEGRATION_NAME}")
            return

        if not public_ingress_integration_exists(self):
            self.unit.status = BlockedStatus(
                f"Missing required relation with {PUBLIC_INGRESS_INTEGRATION_NAME}"
            )
            return

        if not login_ui_integration_exists(self):
            self.unit.status = BlockedStatus(
                f"Missing required relation with {LOGIN_UI_INTEGRATION_NAME}"
            )
            return

        if not self.public_ingress.is_ready():
            self.unit.status = WaitingStatus("Waiting for ingress to be ready")
            return

        public_ingress = PublicIngressData.load(self.public_ingress)
        if not self.dev_mode and not public_ingress.secured:
            self.unit.status = BlockedStatus(
                "Requires a secure (HTTPS) public ingress. "
                "Either enable HTTPS on public ingress or set 'dev' config to true for local development."
            )
            return

        if not LoginUIEndpointData.load(self.login_ui_requirer).is_ready():
            self.unit.status = WaitingStatus("Waiting for login UI to be ready")
            return

        if not self.database_requirer.is_resource_created():
            self.unit.status = WaitingStatus("Waiting for database creation")
            return

        if self.migration_needed:
            self.unit.status = WaitingStatus(
                "Waiting for migration to run, try running the `run-migration` action"
            )
            return

        if not self.secrets.is_ready:
            self.unit.status = WaitingStatus("Waiting for secrets creation")
            event.defer()
            return

        changed = self._pebble_service.update_config_file(
            ConfigFile.from_sources(
                self.secrets,
                self.charm_config,
                DatabaseConfig.load(self.database_requirer),
                LoginUIEndpointData.load(self.login_ui_requirer),
                public_ingress,
                HydraHookData.load(self.token_hook),
            ),
        )

        try:
            self._pebble_service.plan(self._pebble_layer, changed)
        except PebbleServiceError as e:
            logger.error(f"Failed to start the service, please check the container logs: {e}")
            self.unit.status = BlockedStatus(
                f"Failed to restart the service, please check the {WORKLOAD_CONTAINER} logs"
            )
            return

        self._clean_up_oauth_relation_clients()
        self.unit.status = ActiveStatus()

    def _on_run_migration(self, event: ActionEvent) -> None:
        if not self._workload_service.is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        if not peer_integration_exists(self):
            event.fail("Peer integration is not ready yet")
            return

        event.log("Start migrating the database")

        timeout = float(event.params.get("timeout", 120))
        try:
            self._cli.migrate(dsn=DatabaseConfig.load(self.database_requirer).dsn, timeout=timeout)
        except MigrationError as err:
            event.fail(f"Database migration failed: {err}")
            return
        else:
            event.log("Successfully migrated the database")

        migration_version = DatabaseConfig.load(self.database_requirer).migration_version
        self.peer_data[migration_version] = self._workload_service.version
        event.log("Successfully updated migration version")

        self._holistic_handler(event)

    def _on_create_oauth_client_action(self, event: ActionEvent) -> None:
        if not self._workload_service.is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        oauth_client = OAuthClient(**event.params)
        if not (created_client := self._cli.create_oauth_client(oauth_client)):
            event.fail("Failed to create the OAuth client. Please check the juju logs")
            return

        event.set_results(created_client.model_dump(by_alias=True, exclude_none=True))

    def _on_get_oauth_client_info_action(self, event: ActionEvent) -> None:
        if not self._workload_service.is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        client_id = event.params["client-id"]
        if not (oauth_client := self._cli.get_oauth_client(client_id)):
            event.fail("Failed to get the OAuth client. Please check the juju logs")
            return

        event.set_results(oauth_client.model_dump(by_alias=True, exclude_none=True))

    def _on_update_oauth_client_action(self, event: ActionEvent) -> None:
        if not self._workload_service.is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        client_id = event.params["client-id"]
        if not (oauth_client := self._cli.get_oauth_client(client_id)):
            event.fail(f"Failed to get the OAuth client {client_id}. Please check the juju logs")
            return

        if oauth_client.managed_by_integration:
            event.fail(
                f"Cannot update the OAuth client {client_id} because it's managed by an `oauth` integration"
            )
            return

        oauth_client = OAuthClient(**{
            **oauth_client.model_dump(by_alias=True, exclude_none=True),
            **event.params,
        })
        if not (updated_oauth_client := self._cli.update_oauth_client(oauth_client)):
            event.fail(
                f"Failed to update the OAuth client {client_id}. Please check the juju logs"
            )
            return

        event.log(f"Successfully updated the OAuth client {client_id}")
        event.set_results(updated_oauth_client.model_dump(by_alias=True, exclude_none=True))

    def _on_delete_oauth_client_action(self, event: ActionEvent) -> None:
        if not self._workload_service.is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        client_id = event.params["client-id"]
        if not (oauth_client := self._cli.get_oauth_client(client_id)):
            event.fail(f"Failed to get the OAuth client {client_id}. Please check the juju logs")
            return

        if oauth_client.managed_by_integration:
            event.fail(
                f"Cannot delete the OAuth client {client_id} because it's managed by an `oauth` integration. "
                f"Please remove the integration first to delete it."
            )
            return

        if not (res := self._cli.delete_oauth_client(client_id)):
            event.fail(
                f"Failed to delete the OAuth client {client_id}. Please check the juju logs"
            )

        event.log(f"Successfully deleted the OAuth client {client_id}")
        event.set_results({"client-id": res})

    def _on_list_oauth_clients_action(self, event: ActionEvent) -> None:
        if not self._workload_service.is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        if not (oauth_clients := self._cli.list_oauth_clients()):
            event.fail("Failed to list OAuth clients. Please check the juju logs")
            return

        event.set_results({
            str(idx): client.client_id for idx, client in enumerate(oauth_clients, start=1)
        })

    def _on_revoke_oauth_client_access_tokens_action(self, event: ActionEvent) -> None:
        if not self._workload_service.is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        client_id = event.params["client-id"]
        if not (res := self._cli.delete_oauth_client_access_tokens(client_id)):
            event.fail(
                f"Failed to revoke the access tokens of the OAuth client {client_id}. Please check juju logs"
            )
            return

        event.log(f"Successfully revoked the access tokens of the OAuth client {client_id}")
        event.set_results({"client-id": res})

    def _on_rotate_key_action(self, event: ActionEvent) -> None:
        if not self._workload_service.is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        if not (jwk_id := self._cli.create_jwk(algorithm=event.params["algorithm"])):
            event.fail("Failed to rotate the JWK. Please check the juju logs")
            return

        event.log("Successfully rotated the JWK")
        event.set_results({"new-key-id": jwk_id})

    def _reconcile_oauth_clients_action(self, event: ActionEvent) -> None:
        if not self.unit.is_leader():
            event.fail("You need to run this action from the leader unit")
            return

        if not self._workload_service.is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        deleted = self._clean_up_oauth_relation_clients()

        event.log(f"Successfully deleted {deleted} clients")

    @leader_unit
    def _clean_up_oauth_relation_clients(self) -> int:
        to_delete = []
        for k in self.peer_data.keys():
            if not k.startswith("oauth_"):
                continue

            rel_id = k[len("oauth_") :]
            rel = self.model.get_relation(OAUTH_INTEGRATION_NAME, relation_id=int(rel_id))
            if rel.active:
                continue

            client = self.peer_data[k]

            try:
                self._cli.delete_oauth_client(client["client_id"])
            except CommandExecError:
                logger.error(
                    f"Failed to delete the OAuth client bound with the oauth integration: {rel_id}."
                    "Please run the 'reconcile-oauth-clients' action."
                )
            except ClientDoesNotExistError:
                pass

            self.oauth_provider.remove_secret(rel)
            to_delete.append(k)

        for r in to_delete:
            self.peer_data.pop(r)

        return len(to_delete)


if __name__ == "__main__":
    main(HydraCharm)
