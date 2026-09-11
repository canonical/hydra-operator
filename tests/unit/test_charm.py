# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from unittest.mock import MagicMock, PropertyMock, call, patch

import pytest
from charmlibs.interfaces.oauth import OAuthProvider
from charms.hydra.v0.hydra_token_hook import HydraHookRequirer
from ops import ActiveStatus, BlockedStatus, WaitingStatus
from ops.testing import Container, Context, PeerRelation, Relation
from pytest_mock import MockerFixture
from unit.conftest import create_state
from yarl import URL

from charm import HydraCharm
from configs import ConfigFile
from constants import (
    DATABASE_INTEGRATION_NAME,
    OAUTH_INTEGRATION_NAME,
    PEER_INTEGRATION_NAME,
    PUBLIC_ROUTE_INTEGRATION_NAME,
    WORKLOAD_CONTAINER,
)
from exceptions import CommandExecError, PebbleServiceError
from integrations import InternalIngressData, PublicRouteData


class TestPebbleReadyEvent:
    """Tests for the Pebble Ready event handler."""

    def test_when_container_not_connected(
        self,
        context: Context,
        peer_relation_ready: PeerRelation,
        db_relation_ready: Relation,
        public_route_relation: Relation,
        login_ui_relation_ready: Relation,
        mocked_holistic_handler: MagicMock,
    ) -> None:
        """Test that the charm waits when the workload container is not yet connected."""
        container = Container(name=WORKLOAD_CONTAINER, can_connect=False)
        relations = [
            peer_relation_ready,
            db_relation_ready,
            public_route_relation,
            login_ui_relation_ready,
        ]
        state = create_state(containers=[container], relations=relations)

        state_out = context.run(context.on.pebble_ready(container), state)

        assert isinstance(state_out.unit_status, WaitingStatus)
        assert not state_out.opened_ports
        mocked_holistic_handler.assert_not_called()

    def test_when_event_emitted(
        self,
        context: Context,
        container: Container,
        hydra_workload_version: str,
        mocked_holistic_handler: MagicMock,
    ) -> None:
        """Test the successful handling of the Pebble Ready event."""
        state = create_state(containers={container})

        state_out = context.run(context.on.pebble_ready(container), state)

        assert state_out.workload_version == hydra_workload_version
        mocked_holistic_handler.assert_called_once()


class TestLeaderElectedEvent:
    """Tests for the Leader Elected event handler."""

    def test_when_event_emitted(
        self,
        context: Context,
        mocked_holistic_handler: MagicMock,
    ) -> None:
        """Test that the leader elected event triggers the holistic handler."""
        state = create_state(
            leader=True,
        )

        context.run(context.on.leader_elected(), state)

        mocked_holistic_handler.assert_called_once()


class TestConfigChangeEvent:
    """Tests for the Config Changed event handler."""

    def test_when_event_emitted(
        self,
        context: Context,
        mocked_holistic_handler: MagicMock,
    ) -> None:
        """Test that configuration changes trigger the necessary handlers."""
        config = {"jwt_access_tokens": False}
        state = create_state(
            config=config,
        )

        context.run(context.on.config_changed(), state)

        mocked_holistic_handler.assert_called_once()

    def test_when_config_changed_updates_hydra_endpoints(
        self,
        context: Context,
        mocked_internal_ingress_data: MagicMock,
        hydra_endpoint_relation: Relation,
        mocked_holistic_handler: MagicMock,
    ) -> None:
        """Test that configuration changes trigger hydra endpoints update."""
        state = create_state(
            leader=True,
            relations=[hydra_endpoint_relation],
            config={"use_ingress_for_relations": False},
        )

        with patch("charm.HydraEndpointsProvider.send_endpoint_relation_data") as mocked_send:
            context.run(context.on.config_changed(), state)
            mocked_send.assert_called_once_with(
                str(mocked_internal_ingress_data.admin_endpoint),
                str(mocked_internal_ingress_data.public_endpoint),
            )


class TestHydraEndpointsReadyEvent:
    """Tests for the internal Hydra Endpoints Ready event."""

    def test_when_event_emitted(
        self,
        context: Context,
        mocked_internal_ingress_data: MagicMock,
        hydra_endpoint_relation: Relation,
    ) -> None:
        """Test that endpoints are sent to the relation data when ready."""
        state = create_state(leader=True, relations=[hydra_endpoint_relation])

        with patch("charm.HydraEndpointsProvider.send_endpoint_relation_data") as mocked:
            context.run(context.on.relation_created(hydra_endpoint_relation), state)
            mocked.assert_called_once_with(
                str(mocked_internal_ingress_data.admin_endpoint),
                str(mocked_internal_ingress_data.public_endpoint),
            )

    def test_when_event_emitted_and_use_ingress_for_relations_disabled(
        self,
        context: Context,
        mocker: MockerFixture,
        hydra_endpoint_relation: Relation,
    ) -> None:
        """Test that endpoints respect use_ingress_for_relations=False."""
        state = create_state(
            leader=True,
            relations=[hydra_endpoint_relation],
            config={"use_ingress_for_relations": False},
        )

        with patch("charm.InternalIngressData.load") as mocked_load:
            mocked_load.return_value = InternalIngressData(
                public_endpoint=URL("http://app.model.svc.cluster.local:4444"),
                admin_endpoint=URL("http://app.model.svc.cluster.local:4445"),
            )
            with patch("charm.HydraEndpointsProvider.send_endpoint_relation_data") as mocked_send:
                context.run(context.on.relation_created(hydra_endpoint_relation), state)
                mocked_load.assert_called_with(mocker.ANY, False)
                mocked_send.assert_called_once_with(
                    "http://app.model.svc.cluster.local:4445",
                    "http://app.model.svc.cluster.local:4444",
                )


class TestPublicRouteJoinedEvent:
    """Tests for the Public Route Joined event."""

    def test_when_event_emitted(
        self,
        context: Context,
        public_route_relation_ready: Relation,
        mocked_holistic_handler: MagicMock,
    ) -> None:
        """Test that joining a public route integration triggers all dependent handlers."""
        state = create_state(relations=[public_route_relation_ready])

        with patch(
            "charm.HydraEndpointsProvider.send_endpoint_relation_data"
        ) as mocked_endpoints_provider:
            context.run(context.on.relation_joined(public_route_relation_ready), state)

        mocked_endpoints_provider.assert_called_once()
        mocked_holistic_handler.assert_called_once()


class TestPublicRouteChangedEvent:
    """Tests for the Public Route Changed event."""

    def test_when_event_emitted(
        self,
        context: Context,
        public_route_relation_ready: Relation,
        mocked_holistic_handler: MagicMock,
    ) -> None:
        """Test that changes in public route integration data trigger all dependent handlers."""
        state = create_state(relations=[public_route_relation_ready])

        with patch(
            "charm.HydraEndpointsProvider.send_endpoint_relation_data"
        ) as mocked_endpoints_provider:
            context.run(context.on.relation_changed(public_route_relation_ready), state)

        mocked_endpoints_provider.assert_called_once()
        mocked_holistic_handler.assert_called_once()


class TestPublicRouteBrokenEvent:
    """Tests for the Public Route Broken event."""

    def test_when_event_emitted(
        self,
        context: Context,
        public_route_relation: Relation,
        mocked_holistic_handler: MagicMock,
    ) -> None:
        """Test that breaking the public route integration triggers the holistic handler."""
        state = create_state(relations=[public_route_relation])

        context.run(context.on.relation_broken(public_route_relation), state)

        mocked_holistic_handler.assert_called_once()


class TestDatabaseCreatedEvent:
    """Tests for the Database Created event handler."""

    def test_when_container_not_connected(
        self,
        context: Context,
        db_relation_ready: Relation,
        public_route_relation: Relation,
        login_ui_relation_ready: Relation,
    ) -> None:
        """Test waiting status when container not connected."""
        container = Container(name=WORKLOAD_CONTAINER, can_connect=False)

        state = create_state(
            containers=[container],
            relations=[db_relation_ready, public_route_relation, login_ui_relation_ready],
        )

        state_out = context.run(context.on.relation_changed(db_relation_ready), state)

        assert state_out.unit_status == WaitingStatus("Container is not connected yet")

    def test_when_peer_integration_not_exists(
        self,
        context: Context,
        db_relation_ready: Relation,
        public_route_relation: Relation,
        login_ui_relation_ready: Relation,
    ) -> None:
        """Test waiting status when peer integration is missing."""
        state = create_state(
            relations=[db_relation_ready, public_route_relation, login_ui_relation_ready],
        )

        state_out = context.run(context.on.relation_changed(db_relation_ready), state)

        assert state_out.unit_status == WaitingStatus(
            f"Missing integration {PEER_INTEGRATION_NAME}"
        )

    @patch("charm.CommandLine.migrate")
    def test_when_migration_not_needed(
        self,
        mocked_cli_migrate: MagicMock,
        context: Context,
        db_relation_ready: Relation,
        peer_relation_ready: PeerRelation,
        login_ui_relation_ready: Relation,
    ) -> None:
        """Test that migration is skipped if 'migration_needed' is False."""
        public_route = Relation(
            PUBLIC_ROUTE_INTEGRATION_NAME,
            remote_app_data={"external_host": "example.com", "scheme": "https"},
        )
        state = create_state(
            relations=[
                db_relation_ready,
                peer_relation_ready,
                public_route,
                login_ui_relation_ready,
            ]
        )

        state_out = context.run(context.on.relation_changed(db_relation_ready), state)

        mocked_cli_migrate.assert_not_called()
        assert isinstance(state_out.unit_status, ActiveStatus)

    @patch("charm.CommandLine.migrate")
    def test_when_not_leader_unit(
        self,
        mocked_cli_migration: MagicMock,
        context: Context,
        db_relation_ready: Relation,
        peer_relation: PeerRelation,
        login_ui_relation_ready: Relation,
        public_route_relation_ready: Relation,
    ) -> None:
        """Test that non-leader units do not perform migration."""
        state = create_state(
            leader=False,
            relations=[
                db_relation_ready,
                peer_relation,
                public_route_relation_ready,
                login_ui_relation_ready,
            ],
        )

        state_out = context.run(context.on.relation_changed(db_relation_ready), state)

        mocked_cli_migration.assert_not_called()
        assert state_out.unit_status == WaitingStatus(
            "Waiting for migration to run, try running the `run-migration` action"
        )

    @patch("charm.CommandLine.migrate")
    def test_when_leader_unit(
        self,
        mocked_cli_migration: MagicMock,
        context: Context,
        db_relation_ready: Relation,
        peer_relation: PeerRelation,
        login_ui_relation_ready: Relation,
        public_route_relation_ready: Relation,
        hydra_workload_version: str,
    ) -> None:
        """Test that the leader unit runs the migration."""
        state = create_state(
            leader=True,
            relations=[
                db_relation_ready,
                peer_relation,
                public_route_relation_ready,
                login_ui_relation_ready,
            ],
        )

        state_out = context.run(context.on.relation_changed(db_relation_ready), state)

        mocked_cli_migration.assert_called_once()
        peer_out = state_out.get_relation(peer_relation.id)
        assert (
            peer_out.local_app_data.get(f"migration_version_{db_relation_ready.id}")
            == f'"{hydra_workload_version}"'
        )
        assert isinstance(state_out.unit_status, ActiveStatus)


class TestDatabaseBrokenEvent:
    """Tests for the Database Broken event."""

    def test_when_event_emitted(
        self,
        context: Context,
        db_relation_ready: Relation,
        mocked_holistic_handler: MagicMock,
    ) -> None:
        """Test that breaking the database integration triggers the holistic handler."""
        state = create_state(
            relations=[db_relation_ready],
        )

        context.run(context.on.relation_broken(db_relation_ready), state)

        mocked_holistic_handler.assert_called_once()


class TestTokenHookReadyEvent:
    """Tests for the Token Hook Ready event."""

    def test_when_event_emitted(
        self,
        context: Context,
        token_hook_relation: Relation,
        mocked_holistic_handler: MagicMock,
    ) -> None:
        """Test that token hook readiness triggers the holistic handler."""
        state = create_state(relations=[token_hook_relation])

        context.run(context.on.custom(HydraHookRequirer.on.ready, token_hook_relation), state)

        mocked_holistic_handler.assert_called_once()


class TestTokenHookUnavailableEvent:
    """Tests for the Token Hook Unavailable event."""

    def test_when_event_emitted(
        self,
        context: Context,
        token_hook_relation: Relation,
        mocked_holistic_handler: MagicMock,
    ) -> None:
        """Test that token hook unavailability triggers the holistic handler."""
        state = create_state(relations=[token_hook_relation])

        context.run(
            context.on.custom(HydraHookRequirer.on.unavailable, token_hook_relation), state
        )

        mocked_holistic_handler.assert_called_once()


class TestOAuthIntegrationCreatedEvent:
    """Tests for the OAuth Integration Created event."""

    def test_when_event_emitted(
        self,
        context: Context,
        mocked_public_route_data: PublicRouteData,
        mocked_internal_ingress_data: InternalIngressData,
        oauth_relation: Relation,
    ) -> None:
        """Test that creating an OAuth integration correctly sets provider info in relation data."""
        state = create_state(leader=True, relations=[oauth_relation])

        expected_public_url = str(mocked_public_route_data.url)
        expected_admin_url = str(mocked_internal_ingress_data.admin_endpoint)

        with (
            patch("charm.ConfigFile.from_sources", return_value=ConfigFile("config")),
            patch("charm.NOOP_CONDITIONS", new=[]),
            patch("charm.EVENT_DEFER_CONDITIONS", new=[]),
            patch("charm.OAuthProvider.set_provider_info_in_relation_data") as mocked_provider,
        ):
            context.run(context.on.relation_created(oauth_relation), state)

        mocked_provider.assert_called_once()
        assert mocked_provider.call_args == call(
            issuer_url=f"{expected_public_url}",
            authorization_endpoint=f"{expected_public_url}/oauth2/auth",
            token_endpoint=f"{expected_public_url}/oauth2/token",
            introspection_endpoint=f"{expected_admin_url}/admin/oauth2/introspect",
            userinfo_endpoint=f"{expected_public_url}/userinfo",
            jwks_endpoint=f"{expected_public_url}/.well-known/jwks.json",
            scope="openid profile email phone",
            groups=None,
            jwt_access_token=True,
        )


@pytest.mark.xfail(
    reason="We no longer remove clients on relation removal, see https://github.com/canonical/hydra-operator/issues/268"
)
class TestOAuthClientDeletedEvent:
    """Tests for the OAuth Client Deleted event."""

    @pytest.fixture(autouse=True)
    def mocked_database_integration(self, mocker: MockerFixture) -> MagicMock:
        return mocker.patch("charm.database_integration_exists", return_value=True)

    @pytest.fixture(autouse=True)
    def mocked_database_integration_data(self, mocker: MockerFixture) -> MagicMock:
        return mocker.patch("charm.DatabaseRequires.is_resource_created", return_value=True)

    @pytest.fixture(autouse=True)
    def mocked_public_route_ready(self, mocker: MockerFixture) -> MagicMock:
        return mocker.patch("charm.TraefikRouteRequirer.is_ready", return_value=True)

    @pytest.fixture(autouse=True)
    def migration_needed(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "charm.HydraCharm.migration_needed", new_callable=PropertyMock, return_value=False
        )

    def test_when_peer_integration_not_exists(
        self,
        context: Context,
        public_route_integration_data: PublicRouteData,
    ) -> None:
        """Test waiting status when peer integration is missing during client deletion."""
        relation = Relation(OAUTH_INTEGRATION_NAME)
        state = create_state(leader=True, relations=[relation], hydra_is_running=True)

        with patch(
            "charm.CommandLine.delete_oauth_client", return_value="client_id"
        ) as mocked_cli:
            state_out = context.run(
                context.on.custom(
                    OAuthProvider.on.client_deleted,
                    relation_id=relation.id,
                ),
                state,
            )

        mocked_cli.assert_not_called()
        assert state_out.unit_status == WaitingStatus(
            f"Missing integration {PEER_INTEGRATION_NAME}"
        )

    def test_when_oauth_client_deletion_failed(
        self,
        context: Context,
        public_route_integration_data: PublicRouteData,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test handling of client deletion failure."""
        relation = Relation(OAUTH_INTEGRATION_NAME)
        app_data = {f"oauth_{relation.id}": json.dumps({"client_id": "client_id"})}
        peer = PeerRelation(PEER_INTEGRATION_NAME, local_app_data=app_data)
        state = create_state(leader=True, relations=[relation, peer], hydra_is_running=True)

        with (
            caplog.at_level("ERROR"),
            patch(
                "charm.CommandLine.delete_oauth_client", side_effect=CommandExecError
            ) as mocked_cli,
        ):
            state_out = context.run(
                context.on.custom(
                    OAuthProvider.on.client_deleted,
                    relation_id=relation.id,
                ),
                state,
            )

        mocked_cli.assert_called_once_with("client_id")
        assert (
            f"Failed to delete the OAuth client bound with the oauth integration: {relation.id}"
            in caplog.text
        )
        peer_out = state_out.get_relation(peer.id)
        key = f"oauth_{relation.id}"
        assert key in peer_out.local_app_data

    def test_when_event_emitted(
        self,
        context: Context,
        public_route_integration_data: PublicRouteData,
    ) -> None:
        """Test successful deletion of OAuth client."""
        relation = Relation(OAUTH_INTEGRATION_NAME)
        app_data = {f"oauth_{relation.id}": json.dumps({"client_id": "client_id"})}
        peer = PeerRelation(PEER_INTEGRATION_NAME, local_app_data=app_data)
        state = create_state(leader=True, relations=[relation, peer], hydra_is_running=True)

        def trigger(charm: HydraCharm):
            charm.oauth_provider.on.client_deleted.emit(
                relation_id=relation.id,
            )

        with patch(
            "charm.CommandLine.delete_oauth_client", return_value="client_id"
        ) as mocked_cli:
            state_out = context.run(trigger, state)

        mocked_cli.assert_called_once_with("client_id")

        peer_out = state_out.get_relation(peer.id)
        key = f"oauth_{relation.id}"
        assert key not in peer_out.local_app_data


class TestHolisticHandler:
    """Tests for the Holistic Handler (update_status/reconciliation)."""

    def test_when_container_not_connected(
        self,
        context: Context,
        peer_relation_ready: PeerRelation,
        db_relation_ready: Relation,
        login_ui_relation_ready: Relation,
        public_route_relation_ready: Relation,
    ) -> None:
        """Test waiting status when container not connected."""
        state = create_state(
            containers=[Container(name=WORKLOAD_CONTAINER, can_connect=False)],
            relations=[
                peer_relation_ready,
                db_relation_ready,
                login_ui_relation_ready,
                public_route_relation_ready,
            ],
        )

        state_out = context.run(context.on.update_status(), state)

        assert state_out.unit_status == WaitingStatus("Container is not connected yet")

    def test_when_database_integration_missing(
        self,
        context: Context,
    ) -> None:
        """Test blocked status when database integration is missing."""
        with patch("charm.database_integration_exists", return_value=False):
            state = create_state()
            state_out = context.run(context.on.update_status(), state)

        assert state_out.unit_status == BlockedStatus(
            f"Missing integration {DATABASE_INTEGRATION_NAME}"
        )

    def test_when_no_public_route_integration(
        self,
        context: Context,
        peer_relation_ready: PeerRelation,
        db_relation_ready: Relation,
        login_ui_relation_ready: Relation,
    ) -> None:
        """Test blocked status when public route integration is missing."""
        state = create_state(
            relations=[peer_relation_ready, db_relation_ready, login_ui_relation_ready]
        )

        with patch("charm.public_route_integration_exists", return_value=False):
            state_out = context.run(context.on.update_status(), state)

        assert state_out.unit_status == BlockedStatus(
            f"Missing required relation with {PUBLIC_ROUTE_INTEGRATION_NAME}"
        )

    def test_when_public_route_not_ready(
        self,
        context: Context,
        public_route_relation: Relation,
        login_ui_relation_ready: Relation,
        db_relation_ready: Relation,
        peer_relation_ready: PeerRelation,
    ) -> None:
        """Test waiting status when public route is not ready."""
        state = create_state(
            relations=[
                peer_relation_ready,
                db_relation_ready,
                public_route_relation,
                login_ui_relation_ready,
            ]
        )

        state_out = context.run(context.on.update_status(), state)

        assert state_out.unit_status == WaitingStatus("Waiting for ingress to be ready")

    def test_when_public_route_not_secured(
        self,
        context: Context,
        login_ui_relation_ready: Relation,
        db_relation_ready: Relation,
        peer_relation_ready: PeerRelation,
    ) -> None:
        """Test blocked status when public route is not secured/HTTPS in production mode."""
        relation = Relation(
            PUBLIC_ROUTE_INTEGRATION_NAME,
            remote_app_data={"external_host": "example.com", "scheme": "http"},
        )
        state = create_state(
            relations=[peer_relation_ready, db_relation_ready, relation, login_ui_relation_ready]
        )

        state_out = context.run(context.on.update_status(), state)

        assert state_out.unit_status == BlockedStatus(
            "Requires a secure (HTTPS) public ingress. "
            "Either enable HTTPS on public ingress or set 'dev' config to true for local development."
        )

    def test_when_database_not_ready(
        self,
        context: Context,
        public_route_relation_ready: Relation,
        login_ui_relation_ready: Relation,
        db_relation: Relation,
        peer_relation_ready: PeerRelation,
    ) -> None:
        """Test waiting status when database is not ready."""
        state = create_state(
            relations=[
                peer_relation_ready,
                db_relation,
                public_route_relation_ready,
                login_ui_relation_ready,
            ]
        )

        with (
            patch("charm.DatabaseRequires.is_resource_created", return_value=False),
        ):
            state_out = context.run(context.on.update_status(), state)

        assert state_out.unit_status == WaitingStatus("Waiting for database creation")

    def test_when_migration_is_needed(
        self,
        context: Context,
        public_route_relation_ready: Relation,
        login_ui_relation_ready: Relation,
        db_relation_ready: Relation,
        peer_relation_ready: PeerRelation,
    ) -> None:
        """Test waiting status when migration is needed."""
        state = create_state(
            relations=[
                peer_relation_ready,
                db_relation_ready,
                public_route_relation_ready,
                login_ui_relation_ready,
            ]
        )

        with (
            patch("charm.migration_is_ready", return_value=False),
        ):
            state_out = context.run(context.on.update_status(), state)

        assert state_out.unit_status == WaitingStatus(
            "Waiting for migration to run, try running the `run-migration` action"
        )

    def test_when_secrets_not_ready(
        self,
        context: Context,
        public_route_relation_ready: Relation,
        login_ui_relation_ready: Relation,
        db_relation_ready: Relation,
        peer_relation_ready: PeerRelation,
    ) -> None:
        """Test waiting status when secrets are not ready."""
        state = create_state(
            relations=[
                peer_relation_ready,
                db_relation_ready,
                public_route_relation_ready,
                login_ui_relation_ready,
            ]
        )

        with (
            patch("charm.secrets_is_ready", return_value=False),
        ):
            state_out = context.run(context.on.update_status(), state)

        assert state_out.unit_status == WaitingStatus("Waiting for secrets creation")

    def test_when_login_ui_not_ready(
        self,
        context: Context,
        public_route_relation_ready: Relation,
        login_ui_relation: Relation,
        db_relation_ready: Relation,
        peer_relation_ready: PeerRelation,
    ) -> None:
        """Test waiting status when login UI is not ready."""
        state = create_state(
            relations=[
                peer_relation_ready,
                db_relation_ready,
                public_route_relation_ready,
                login_ui_relation,
            ]
        )

        state_out = context.run(context.on.update_status(), state)

        assert state_out.unit_status == WaitingStatus("Waiting for login UI to be ready")

    def test_when_pebble_plan_failed(
        self,
        context: Context,
        public_route_relation_ready: Relation,
        login_ui_relation_ready: Relation,
        db_relation_ready: Relation,
        peer_relation_ready: PeerRelation,
    ) -> None:
        """Test blocked status when Pebble plan fails."""
        state = create_state(
            relations=[
                peer_relation_ready,
                db_relation_ready,
                public_route_relation_ready,
                login_ui_relation_ready,
            ]
        )

        with (
            patch("charm.ConfigFile.from_sources", return_value=ConfigFile("config")),
            patch("charm.NOOP_CONDITIONS", new=[]),
            patch("charm.EVENT_DEFER_CONDITIONS", new=[]),
            patch("charm.PebbleService.plan", side_effect=PebbleServiceError),
            patch("charm.WorkloadService.is_failing", return_value=True),
            # Patch all checks to True
            patch("charm.login_ui_is_ready", return_value=True),
            patch("charm.database_resource_is_created", return_value=True),
            patch("charm.secrets_is_ready", return_value=True),
        ):
            state_out = context.run(context.on.update_status(), state)

        assert state_out.unit_status == BlockedStatus(
            f"Failed to start the service, please check the {WORKLOAD_CONTAINER} container logs"
        )

    def test_when_succeeds(
        self,
        context: Context,
        public_route_relation_ready: Relation,
        login_ui_relation_ready: Relation,
        db_relation_ready: Relation,
        peer_relation_ready: PeerRelation,
    ) -> None:
        """Test active status when all conditions are met."""
        state = create_state(
            relations=[
                peer_relation_ready,
                db_relation_ready,
                public_route_relation_ready,
                login_ui_relation_ready,
            ]
        )

        with (
            patch("charm.ConfigFile.from_sources", return_value=ConfigFile("config")),
            patch("charm.NOOP_CONDITIONS", new=[]),
            patch("charm.EVENT_DEFER_CONDITIONS", new=[]),
            patch("charm.WorkloadService.is_running", return_value=True),
            patch("charm.login_ui_is_ready", return_value=True),
            patch("charm.database_resource_is_created", return_value=True),
            patch("charm.secrets_is_ready", return_value=True),
        ):
            state_out = context.run(context.on.update_status(), state)

        assert state_out.unit_status == ActiveStatus()

    def test_does_not_publish_oauth_provider_info_when_not_ready(
        self,
        context: Context,
        public_route_relation_ready: Relation,
        oauth_relation: Relation,
    ) -> None:
        """Test that a blocked charm does not advertise endpoints it cannot serve."""
        state = create_state(relations=[public_route_relation_ready, oauth_relation])

        with patch("charm.OAuthProvider.set_provider_info_in_relation_data") as mocked_provider:
            state_out = context.run(context.on.update_status(), state)

        assert isinstance(state_out.unit_status, BlockedStatus)
        mocked_provider.assert_not_called()

    def test_publishes_oauth_provider_info_when_ready(
        self,
        context: Context,
        public_route_relation_ready: Relation,
        login_ui_relation_ready: Relation,
        db_relation_ready: Relation,
        peer_relation_ready: PeerRelation,
        oauth_relation: Relation,
    ) -> None:
        """Test that provider info is published once every readiness condition is met."""
        state = create_state(
            relations=[
                peer_relation_ready,
                db_relation_ready,
                public_route_relation_ready,
                login_ui_relation_ready,
                oauth_relation,
            ]
        )

        with (
            patch("charm.ConfigFile.from_sources", return_value=ConfigFile("config")),
            patch("charm.NOOP_CONDITIONS", new=[]),
            patch("charm.EVENT_DEFER_CONDITIONS", new=[]),
            patch("charm.WorkloadService.is_running", return_value=True),
            patch("charm.OAuthProvider.set_provider_info_in_relation_data") as mocked_provider,
        ):
            context.run(context.on.update_status(), state)

        mocked_provider.assert_called_once()
