#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""A Juju charm for Ory Hydra."""

import json
import logging
from os.path import join
from typing import Any, Dict, Optional

from charms.data_platform_libs.v0.data_interfaces import (
    DatabaseCreatedEvent,
    DatabaseEndpointsChangedEvent,
    DatabaseRequires,
)
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
    HookEvent,
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
    WaitingStatus,
)
from ops.pebble import ChangeError, Error, ExecError, Layer

from hydra_cli import HydraCLI

logger = logging.getLogger(__name__)

EXTRA_USER_ROLES = "SUPERUSER"
HYDRA_ADMIN_PORT = 4445
HYDRA_PUBLIC_PORT = 4444
SUPPORTED_SCOPES = ["openid", "profile", "email", "phone"]
PEER = "hydra"


def remove_none_values(dic: Dict) -> Dict:
    """Remove all entries in a dict with `None` values."""
    return {k: v for k, v in dic.items() if v is not None}


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

        self._hydra_cli = HydraCLI(f"http://localhost:{HYDRA_ADMIN_PORT}", self._container)

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
        self.oauth = OAuthProvider(self)

        self.login_ui_endpoints = LoginUIEndpointsRequirer(
            self, relation_name=self._login_ui_relation_name
        )

        self.endpoints_provider = HydraEndpointsProvider(self)

        self.framework.observe(self.on.hydra_pebble_ready, self._on_hydra_pebble_ready)
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

    @property
    def _hydra_service_is_created(self) -> bool:
        try:
            self._container.get_service(self._container_name)
        except (ModelError, RuntimeError):
            return False
        return True

    @property
    def _hydra_service_is_running(self) -> bool:
        if not self._container.can_connect():
            return False

        try:
            service = self._container.get_service(self._container_name)
        except (ModelError, RuntimeError):
            return False
        return service.is_running()

    def _render_conf_file(self) -> str:
        """Render the Hydra configuration file."""
        with open("templates/hydra.yaml.j2", "r") as file:
            template = Template(file.read())

        rendered = template.render(
            db_info=self._get_database_relation_info(),
            consent_url=self._get_login_ui_endpoint_info("consent_url"),
            error_url=self._get_login_ui_endpoint_info("oidc_error_url"),
            login_url=self._get_login_ui_endpoint_info("login_url"),
            hydra_public_url=self.public_ingress.url
            if self.public_ingress.is_ready()
            else f"http://127.0.0.1:{HYDRA_PUBLIC_PORT}/",
            supported_scopes=SUPPORTED_SCOPES,
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

    def _oauth_relation_peer_data_key(self, relation_id: int) -> str:
        return f"oauth_{relation_id}"

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

    def _handle_status_update_config(self, event: HookEvent) -> None:
        if not self._container.can_connect():
            event.defer()
            logger.info("Cannot connect to Hydra container. Deferring the event.")
            self.unit.status = WaitingStatus("Waiting to connect to Hydra container")
            return

        self.unit.status = MaintenanceStatus("Configuring resources")

        current_layer = self._container.get_plan()
        new_layer = self._hydra_layer
        if current_layer.services != new_layer.services:
            self._container.add_layer(self._container_name, self._hydra_layer, combine=True)
            logger.info("Pebble plan updated with new configuration, replanning")
            try:
                self._container.replan()
            except ChangeError as err:
                logger.error(str(err))
                self.unit.status = BlockedStatus("Failed to replan, please consult the logs")
                return

        if not self._hydra_service_is_created:
            event.defer()
            self.unit.status = WaitingStatus("Waiting for Hydra service")
            logger.info("Hydra service is absent. Deferring the event.")
            return

        if not self.model.relations[self._db_relation_name]:
            self.unit.status = BlockedStatus("Missing required relation with postgresql")
            return

        if not self.database.is_resource_created():
            self.unit.status = WaitingStatus("Waiting for database creation")
            return

        self._container.push(self._hydra_config_path, self._render_conf_file(), make_dirs=True)
        self._container.restart(self._container_name)
        self.unit.status = ActiveStatus()

    def _update_hydra_endpoints_relation_data(self, event: RelationEvent) -> None:
        logger.info("Sending endpoints info")

        admin_endpoint = (
            f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{HYDRA_ADMIN_PORT}"
        )
        public_endpoint = (
            f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{HYDRA_PUBLIC_PORT}"
        )
        self.endpoints_provider.send_endpoint_relation_data(admin_endpoint, public_endpoint)

    def _on_hydra_pebble_ready(self, event: WorkloadEvent) -> None:
        """Event Handler for pebble ready event."""
        self._handle_status_update_config(event)

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

        if not self._hydra_service_is_created:
            event.defer()
            self.unit.status = WaitingStatus("Waiting for Hydra service")
            logger.info("Hydra service is absent. Deferring the event.")
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
        self._handle_status_update_config(event)

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

        self._update_endpoint_info(event)

    def _on_public_ingress_ready(self, event: IngressPerAppReadyEvent) -> None:
        if self.unit.is_leader():
            logger.info("This app's public ingress URL: %s", event.url)

        self._handle_status_update_config(event)
        self._update_endpoint_info(event)

    def _on_ingress_revoked(self, event: IngressPerAppRevokedEvent) -> None:
        if self.unit.is_leader():
            logger.info("This app no longer has ingress")

        self._handle_status_update_config(event)
        self._update_endpoint_info(event)

    def _on_oauth_relation_created(self, event: RelationCreatedEvent) -> None:
        self._update_endpoint_info(event)

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

    def _update_endpoint_info(self, event: RelationEvent) -> None:
        if not self.admin_ingress.url or not self.public_ingress.url:
            event.defer()
            logger.info("Ingress URL not available. Deferring the event.")
            return

        self.oauth.set_provider_info_in_relation_data(
            issuer_url=self.public_ingress.url,
            authorization_endpoint=join(self.public_ingress.url, "oauth2/auth"),
            token_endpoint=join(self.public_ingress.url, "oauth2/token"),
            introspection_endpoint=join(self.admin_ingress.url, "admin/oauth2/introspect"),
            userinfo_endpoint=join(self.public_ingress.url, "userinfo"),
            jwks_endpoint=join(self.public_ingress.url, ".well-known/jwks.json"),
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


if __name__ == "__main__":
    main(HydraCharm)
