# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, PropertyMock, call, patch

import pytest
from ops import ActiveStatus, BlockedStatus, WaitingStatus
from ops.testing import Harness
from pytest_mock import MockerFixture

from cli import OAuthClient
from configs import ConfigFile
from constants import (
    DATABASE_INTEGRATION_NAME,
    HYDRA_TOKEN_HOOK_INTEGRATION_NAME,
    OAUTH_INTEGRATION_NAME,
    PEER_INTEGRATION_NAME,
    PUBLIC_INGRESS_INTEGRATION_NAME,
    WORKLOAD_CONTAINER,
)
from exceptions import CommandExecError, PebbleServiceError
from integrations import InternalIngressData, PublicIngressData


class TestPebbleReadyEvent:
    def test_when_container_not_connected(
        self,
        harness: Harness,
        mocked_pebble_service: MagicMock,
        mocked_workload_service: MagicMock,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        harness.set_can_connect(WORKLOAD_CONTAINER, False)

        container = harness.model.unit.get_container(WORKLOAD_CONTAINER)
        harness.charm.on.hydra_pebble_ready.emit(container)

        assert isinstance(harness.model.unit.status, WaitingStatus)
        mocked_pebble_service.prepare_dir.assert_not_called()
        mocked_workload_service.open_port.assert_not_called()
        mocked_charm_holistic_handler.assert_not_called()

    def test_when_event_emitted(
        self,
        harness: Harness,
        mocked_pebble_service: MagicMock,
        mocked_workload_service_version: MagicMock,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        container = harness.model.unit.get_container(WORKLOAD_CONTAINER)
        harness.charm.on.hydra_pebble_ready.emit(container)

        mocked_charm_holistic_handler.assert_called_once()
        assert mocked_workload_service_version.call_count > 1, (
            "workload service version should be set"
        )
        assert mocked_workload_service_version.call_args[0] == (
            mocked_workload_service_version.return_value,
        )


class TestLeaderElectedEvent:
    @patch("charm.Secrets")
    def test_when_secrets_ready(self, mocked_secrets: MagicMock, harness: Harness) -> None:
        harness.charm.secrets = mocked_secrets
        mocked_secrets.is_ready = True

        harness.set_leader(True)

        mocked_secrets.__setitem__.assert_not_called()

    def test_when_event_emitted(self, harness: Harness) -> None:
        harness.set_leader(True)

        secrets = harness.charm.secrets
        assert secrets.is_ready is True


class TestConfigChangeEvent:
    def test_when_event_emitted(
        self,
        harness: Harness,
        mocked_charm_holistic_handler: MagicMock,
        mocked_oauth_integration_created_handler: MagicMock,
    ) -> None:
        harness.update_config({"jwt_access_tokens": False})

        mocked_charm_holistic_handler.assert_called_once()
        mocked_oauth_integration_created_handler.assert_called_once()


class TestHydraEndpointsReadyEvent:
    def test_when_event_emitted(
        self,
        harness: MagicMock,
        mocked_internal_ingress_data: MagicMock,
    ) -> None:
        with patch("charm.HydraEndpointsProvider.send_endpoint_relation_data") as mocked:
            harness.charm.hydra_endpoints_provider.on.ready.emit()

        mocked.assert_called_once_with(
            str(mocked_internal_ingress_data.admin_endpoint),
            str(mocked_internal_ingress_data.public_endpoint),
        )


class TestPublicIngressReadyEvent:
    def test_when_event_emitted(
        self,
        harness: Harness,
        public_ingress_integration: int,
        mocked_charm_holistic_handler: MagicMock,
        mocked_oauth_integration_created_handler: MagicMock,
        mocked_hydra_endpoints_ready_handler: MagicMock,
    ) -> None:
        harness.charm.public_ingress.on.ready.emit(
            harness.model.get_relation("public-ingress"), "url"
        )

        mocked_charm_holistic_handler.assert_called_once()
        mocked_oauth_integration_created_handler.assert_called_once()
        mocked_hydra_endpoints_ready_handler.assert_called_once()


class TestPublicIngressRevokedEvent:
    def test_when_event_emitted(
        self,
        harness: Harness,
        public_ingress_integration: int,
        mocked_charm_holistic_handler: MagicMock,
        mocked_oauth_integration_created_handler: MagicMock,
        mocked_hydra_endpoints_ready_handler: MagicMock,
    ) -> None:
        harness.charm.public_ingress.on.revoked.emit(harness.model.get_relation("public-ingress"))

        mocked_charm_holistic_handler.assert_called_once()
        mocked_oauth_integration_created_handler.assert_called_once()
        mocked_hydra_endpoints_ready_handler.assert_called_once()


class TestDatabaseCreatedEvent:
    @pytest.fixture(autouse=True)
    def mocked_secrets(self, mocker: MockerFixture, harness: Harness) -> MagicMock:
        mocked = mocker.patch("charm.Secrets", autospec=True)
        mocked.is_ready = True
        harness.charm.secrets = mocked
        return mocked

    @pytest.fixture(autouse=True)
    def migration_needed(self, mocker: MockerFixture, harness: Harness) -> None:
        mocker.patch(
            "charm.HydraCharm.migration_needed", new_callable=PropertyMock, return_value=True
        )

    def test_when_container_not_connected(
        self,
        harness: Harness,
        database_integration: int,
        peer_integration: int,
    ) -> None:
        harness.set_can_connect(WORKLOAD_CONTAINER, False)

        harness.charm.database_requirer.on.database_created.emit(
            harness.model.get_relation(DATABASE_INTEGRATION_NAME)
        )
        assert harness.model.unit.status == WaitingStatus("Container is not connected yet")

    def test_when_peer_integration_not_exists(
        self,
        harness: Harness,
        database_integration: int,
    ) -> None:
        harness.charm.database_requirer.on.database_created.emit(
            harness.model.get_relation(DATABASE_INTEGRATION_NAME)
        )
        assert harness.model.unit.status == WaitingStatus(
            f"Missing integration {PEER_INTEGRATION_NAME}"
        )

    def test_when_secrets_not_ready(
        self,
        harness: Harness,
        database_integration: int,
        peer_integration: int,
        mocked_secrets: MagicMock,
    ) -> None:
        mocked_secrets.is_ready = False
        harness.charm.database_requirer.on.database_created.emit(
            harness.model.get_relation(DATABASE_INTEGRATION_NAME)
        )
        assert harness.model.unit.status == WaitingStatus("Missing required secrets")

    @patch("charm.CommandLine.migrate")
    def test_when_migration_not_needed(
        self,
        mocked_cli_migrate: MagicMock,
        harness: Harness,
        database_integration: int,
        peer_integration: int,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        with patch(
            "charm.HydraCharm.migration_needed", new_callable=PropertyMock, return_value=False
        ):
            harness.charm.database_requirer.on.database_created.emit(
                harness.model.get_relation(DATABASE_INTEGRATION_NAME)
            )

        mocked_charm_holistic_handler.assert_called_once()
        mocked_cli_migrate.assert_not_called()

    @patch("charm.CommandLine.migrate")
    def test_when_not_leader_unit(
        self,
        mocked_cli_migration: MagicMock,
        harness: Harness,
        database_integration: int,
        peer_integration: int,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        harness.charm.database_requirer.on.database_created.emit(
            harness.model.get_relation(DATABASE_INTEGRATION_NAME)
        )

        mocked_cli_migration.assert_not_called()
        mocked_charm_holistic_handler.assert_not_called()
        assert harness.model.unit.status == WaitingStatus(
            "Waiting for leader unit to run the migration"
        )

    @patch("charm.CommandLine.migrate")
    def test_when_leader_unit(
        self,
        mocked_cli_migration: MagicMock,
        harness: Harness,
        database_integration: int,
        peer_integration: int,
        mocked_charm_holistic_handler: MagicMock,
        mocked_workload_service_version: MagicMock,
    ) -> None:
        harness.set_leader(True)

        harness.charm.database_requirer.on.database_created.emit(
            harness.model.get_relation(DATABASE_INTEGRATION_NAME)
        )

        mocked_cli_migration.assert_called_once()
        mocked_charm_holistic_handler.assert_called_once()

        assert (
            harness.charm.peer_data[f"migration_version_{database_integration}"]
            == mocked_workload_service_version.return_value
        ), "migration version should be set in peer data"


class TestDatabaseChangedEvent:
    def test_when_event_emitted(
        self,
        harness: Harness,
        database_integration: int,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        harness.charm.database_requirer.on.endpoints_changed.emit(
            harness.model.get_relation(DATABASE_INTEGRATION_NAME),
        )

        mocked_charm_holistic_handler.assert_called_once()


class TestDatabaseBrokenEvent:
    def test_when_event_emitted(
        self,
        harness: Harness,
        database_integration: int,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        harness.charm.on[DATABASE_INTEGRATION_NAME].relation_broken.emit(
            harness.model.get_relation(DATABASE_INTEGRATION_NAME),
        )

        mocked_charm_holistic_handler.assert_called_once()


class TestTokenHookReadyEvent:
    def test_when_event_emitted(
        self,
        harness: Harness,
        token_hook_integration: int,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        harness.charm.token_hook.on.ready.emit(
            harness.model.get_relation(HYDRA_TOKEN_HOOK_INTEGRATION_NAME),
        )

        mocked_charm_holistic_handler.assert_called_once()


class TestTokenHookUnavailableEvent:
    def test_when_event_emitted(
        self,
        harness: Harness,
        token_hook_integration: int,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        harness.charm.token_hook.on.unavailable.emit(
            harness.model.get_relation(HYDRA_TOKEN_HOOK_INTEGRATION_NAME),
        )

        mocked_charm_holistic_handler.assert_called_once()


class TestOAuthIntegrationCreatedEvent:
    def test_when_event_emitted(
        self,
        harness: Harness,
        mocked_public_ingress_data: PublicIngressData,
        mocked_internal_ingress_data: InternalIngressData,
        oauth_integration: int,
    ) -> None:
        with patch("charm.OAuthProvider.set_provider_info_in_relation_data") as mocked_provider:
            harness.charm.on.oauth_relation_created.emit(
                harness.model.get_relation(OAUTH_INTEGRATION_NAME),
            )
        expected_public_url = str(mocked_public_ingress_data.url)
        expected_admin_url = str(mocked_internal_ingress_data.admin_endpoint)
        mocked_provider.assert_called_once()
        assert mocked_provider.call_args == call(
            issuer_url=f"{expected_public_url}",
            authorization_endpoint=f"{expected_public_url}/oauth2/auth",
            token_endpoint=f"{expected_public_url}/oauth2/token",
            introspection_endpoint=f"{expected_admin_url}/admin/oauth2/introspect",
            userinfo_endpoint=f"{expected_public_url}/userinfo",
            jwks_endpoint=f"{expected_public_url}/.well-known/jwks.json",
            scope="openid profile email phone",
            jwt_access_token=True,
        )


class TestOAuthClientCreatedEvent:
    def test_when_hydra_service_not_ready(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        mocked_oauth_client_config: dict,
        peer_integration: int,
        oauth_integration: int,
    ) -> None:
        harness.set_leader(True)
        mocked_workload_service.is_running = False

        with patch("charm.CommandLine.create_oauth_client") as mocked_cli:
            harness.charm.oauth_provider.on.client_created.emit(
                relation_id=oauth_integration, **mocked_oauth_client_config
            )

        mocked_cli.assert_not_called()
        assert harness.charm.unit.status == WaitingStatus("Waiting for Hydra service")

    def test_when_peer_integration_not_exists(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        mocked_oauth_client_config: dict,
        oauth_integration: int,
    ) -> None:
        harness.set_leader(True)
        mocked_workload_service.is_running = True

        with patch("charm.CommandLine.create_oauth_client") as mocked_cli:
            harness.charm.oauth_provider.on.client_created.emit(
                relation_id=oauth_integration, **mocked_oauth_client_config
            )

        mocked_cli.assert_not_called()
        assert harness.charm.unit.status == WaitingStatus(
            f"Missing integration {PEER_INTEGRATION_NAME}"
        )

    def test_when_oauth_client_creation_failed(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        mocked_oauth_client_config: dict,
        peer_integration: int,
        oauth_integration: int,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        harness.set_leader(True)
        mocked_workload_service.is_running = True

        with (
            caplog.at_level("ERROR"),
            patch(
                "charm.CommandLine.create_oauth_client",
                return_value=None,
            ),
            patch(
                "charm.OAuthProvider.set_client_credentials_in_relation_data"
            ) as mocked_provider,
        ):
            harness.charm.oauth_provider.on.client_created.emit(
                relation_id=oauth_integration, **mocked_oauth_client_config
            )

        assert "Failed to create the OAuth client bound with the oauth integration" in caplog.text
        assert not harness.charm.peer_data[f"oauth_{oauth_integration}"], (
            "peer data should NOT be created"
        )
        mocked_provider.assert_not_called()

    def test_when_succeeds(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        mocked_oauth_client_config: dict,
        peer_integration: int,
        oauth_integration: int,
    ) -> None:
        harness.set_leader(True)
        mocked_workload_service.is_running = True

        with (
            patch(
                "charm.CommandLine.create_oauth_client",
                return_value=OAuthClient(client_id="client_id", client_secret="client_secret"),
            ),
            patch(
                "charm.OAuthProvider.set_client_credentials_in_relation_data"
            ) as mocked_provider,
        ):
            harness.charm.oauth_provider.on.client_created.emit(
                relation_id=oauth_integration, **mocked_oauth_client_config
            )

        assert harness.charm.peer_data[f"oauth_{oauth_integration}"] == {"client_id": "client_id"}
        mocked_provider.assert_called_once_with(oauth_integration, "client_id", "client_secret")

    def test_client_created_emitted_twice(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        mocked_oauth_client_config: dict,
        peer_integration: int,
        oauth_integration: int,
    ) -> None:
        harness.set_leader(True)
        mocked_workload_service.is_running = True

        with (
            patch(
                "charm.CommandLine.create_oauth_client",
                return_value=OAuthClient(client_id="client_id", client_secret="client_secret"),
            ),
            patch(
                "charm.OAuthProvider.set_client_credentials_in_relation_data"
            ) as mocked_provider,
        ):
            harness.charm.oauth_provider.on.client_created.emit(
                relation_id=oauth_integration, **mocked_oauth_client_config
            )
            harness.charm.oauth_provider.on.client_created.emit(
                relation_id=oauth_integration, **mocked_oauth_client_config
            )

        assert harness.charm.peer_data[f"oauth_{oauth_integration}"] == {"client_id": "client_id"}
        mocked_provider.assert_called_once()


class TestOAuthClientChangedEvent:
    def test_when_hydra_service_not_ready(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        mocked_oauth_client_config: dict,
        oauth_integration: int,
    ) -> None:
        harness.set_leader(True)
        mocked_workload_service.is_running = False

        with patch("charm.CommandLine.update_oauth_client") as mocked_cli:
            harness.charm.oauth_provider.on.client_changed.emit(
                relation_id=oauth_integration, client_id="client_id", **mocked_oauth_client_config
            )

        mocked_cli.assert_not_called()
        assert harness.charm.unit.status == WaitingStatus("Waiting for Hydra service")

    def test_when_oauth_client_update_failed(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        mocked_oauth_client_config: dict,
        oauth_integration: int,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        harness.set_leader(True)
        mocked_workload_service.is_running = True

        with (
            caplog.at_level("ERROR"),
            patch("charm.CommandLine.update_oauth_client", return_value=None) as mocked_cli,
        ):
            harness.charm.oauth_provider.on.client_changed.emit(
                relation_id=oauth_integration, client_id="client_id", **mocked_oauth_client_config
            )

        mocked_cli.assert_called_once()
        assert (
            f"Failed to update the OAuth client bound with the oauth integration: {oauth_integration}"
            in caplog.text
        )


@pytest.mark.xfail(
    reason="We no longer remove clients on relation removal, see https://github.com/canonical/hydra-operator/issues/268"
)
class TestOAuthClientDeletedEvent:
    @pytest.fixture(autouse=True)
    def mocked_database_integration(self, mocker: MockerFixture) -> MagicMock:
        return mocker.patch("charm.database_integration_exists", return_value=True)

    @pytest.fixture(autouse=True)
    def mocked_database_integration_data(self, mocker: MockerFixture) -> MagicMock:
        return mocker.patch("charm.DatabaseRequires.is_resource_created", return_value=True)

    @pytest.fixture(autouse=True)
    def mocked_public_ingress_ready(self, mocker: MockerFixture) -> MagicMock:
        return mocker.patch("charm.IngressPerAppRequirer.is_ready", return_value=True)

    @pytest.fixture(autouse=True)
    def migration_needed(self, mocker: MockerFixture, harness: Harness) -> None:
        mocker.patch(
            "charm.HydraCharm.migration_needed", new_callable=PropertyMock, return_value=False
        )

    def test_when_peer_integration_not_exists(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        public_ingress_integration_data: PublicIngressData,
        oauth_integration: int,
    ) -> None:
        harness.set_leader(True)
        mocked_workload_service.is_running = True

        with patch(
            "charm.CommandLine.delete_oauth_client", return_value="client_id"
        ) as mocked_cli:
            harness.charm.oauth_provider.on.client_deleted.emit(
                relation_id=oauth_integration,
            )

        mocked_cli.assert_not_called()
        assert harness.charm.unit.status == WaitingStatus(
            f"Missing integration {PEER_INTEGRATION_NAME}"
        )

    def test_when_oauth_client_deletion_failed(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        public_ingress_integration_data: PublicIngressData,
        peer_integration: int,
        oauth_integration: int,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        harness.set_leader(True)
        mocked_workload_service.is_running = True
        harness.charm.peer_data[f"oauth_{oauth_integration}"] = {"client_id": "client_id"}
        harness.model.get_relation(OAUTH_INTEGRATION_NAME, oauth_integration).active = False

        with (
            caplog.at_level("ERROR"),
            patch(
                "charm.CommandLine.delete_oauth_client", side_effect=CommandExecError
            ) as mocked_cli,
        ):
            harness.charm.oauth_provider.on.client_deleted.emit(
                relation_id=oauth_integration,
            )

        mocked_cli.assert_called_once_with("client_id")
        assert (
            f"Failed to delete the OAuth client bound with the oauth integration: {oauth_integration}"
            in caplog.text
        )
        assert harness.charm.peer_data[f"oauth_{oauth_integration}"], (
            "peer data should NOT be cleared"
        )

    def test_when_event_emitted(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        public_ingress_integration_data: PublicIngressData,
        peer_integration: int,
        oauth_integration: int,
    ) -> None:
        harness.set_leader(True)
        mocked_workload_service.is_running = True
        harness.charm.peer_data[f"oauth_{oauth_integration}"] = {"client_id": "client_id"}
        harness.model.get_relation(OAUTH_INTEGRATION_NAME, oauth_integration).active = False

        with patch(
            "charm.CommandLine.delete_oauth_client", return_value="client_id"
        ) as mocked_cli:
            harness.charm.oauth_provider.on.client_deleted.emit(
                relation_id=oauth_integration,
            )

        mocked_cli.assert_called_once_with("client_id")
        assert not harness.charm.peer_data[f"oauth_{oauth_integration}"], (
            "peer data should be cleared"
        )


class TestHolisticHandler:
    @pytest.fixture(autouse=True)
    def mocked_database_integration(self, mocker: MockerFixture) -> MagicMock:
        return mocker.patch("charm.database_integration_exists", return_value=True)

    @pytest.fixture(autouse=True)
    def mocked_database_integration_data(self, mocker: MockerFixture) -> MagicMock:
        return mocker.patch("charm.DatabaseRequires.is_resource_created", return_value=True)

    @pytest.fixture(autouse=True)
    def mocked_public_ingress_ready(self, mocker: MockerFixture) -> MagicMock:
        return mocker.patch("charm.IngressPerAppRequirer.is_ready", return_value=True)

    @pytest.fixture(autouse=True)
    def mocked_secrets(self, mocker: MockerFixture, harness: Harness) -> MagicMock:
        mocked = mocker.patch("charm.Secrets", autospec=True)
        mocked.is_ready = True
        harness.charm.secrets = mocked
        return mocked

    @pytest.fixture(autouse=True)
    def migration_needed(self, mocker: MockerFixture, harness: Harness) -> None:
        mocker.patch(
            "charm.HydraCharm.migration_needed", new_callable=PropertyMock, return_value=False
        )

    @pytest.fixture
    def non_dev_mode(self, mocker: MockerFixture) -> None:
        mocker.patch("charm.HydraCharm.dev_mode", new_callable=PropertyMock, return_value=False)

    @pytest.fixture
    def non_secured_ingress(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "charm.PublicIngressData.secured", new_callable=PropertyMock, return_value=False
        )

    def test_when_container_not_connected(
        self,
        harness: Harness,
        mocked_event: MagicMock,
        mocked_pebble_service: MagicMock,
    ) -> None:
        harness.set_can_connect(WORKLOAD_CONTAINER, False)

        harness.charm._holistic_handler(mocked_event)

        mocked_pebble_service.update_config_file.assert_not_called()
        mocked_pebble_service.plan.assert_not_called()
        assert harness.charm.unit.status == WaitingStatus("Container is not connected yet")

    def test_when_database_integration_missing(
        self,
        harness: Harness,
        mocked_event: MagicMock,
        peer_integration: int,
        mocked_pebble_service: MagicMock,
    ) -> None:
        with patch("charm.database_integration_exists", return_value=False):
            harness.charm._holistic_handler(mocked_event)

        mocked_pebble_service.update_config_file.assert_not_called()
        mocked_pebble_service.plan.assert_not_called()
        assert harness.charm.unit.status == BlockedStatus(
            f"Missing integration {DATABASE_INTEGRATION_NAME}"
        )

    def test_when_no_public_ingress_integration(
        self,
        harness: Harness,
        mocked_event: MagicMock,
        peer_integration: int,
        mocked_pebble_service: MagicMock,
    ) -> None:
        with patch("charm.IngressPerAppRequirer.is_ready", return_value=False):
            harness.charm._holistic_handler(mocked_event)

        mocked_pebble_service.update_config_file.assert_not_called()
        mocked_pebble_service.plan.assert_not_called()
        assert harness.charm.unit.status == BlockedStatus(
            f"Missing required relation with {PUBLIC_INGRESS_INTEGRATION_NAME}"
        )

    def test_when_public_ingress_not_ready(
        self,
        harness: Harness,
        mocked_event: MagicMock,
        mocked_pebble_service: MagicMock,
        peer_integration: int,
        login_ui_integration: int,
        public_ingress_integration: MagicMock,
    ) -> None:
        with patch("charm.IngressPerAppRequirer.is_ready", return_value=False):
            harness.charm._holistic_handler(mocked_event)

        mocked_pebble_service.update_config_file.assert_not_called()
        mocked_pebble_service.plan.assert_not_called()
        assert harness.charm.unit.status == WaitingStatus("Waiting for ingress to be ready")

    def test_when_public_ingress_not_secured(
        self,
        harness: Harness,
        mocked_event: MagicMock,
        mocked_pebble_service: MagicMock,
        non_dev_mode: None,
        non_secured_ingress: None,
        peer_integration: int,
        login_ui_integration_data: None,
        public_ingress_integration_data: None,
    ) -> None:
        harness.charm._holistic_handler(mocked_event)

        mocked_pebble_service.update_config_file.assert_not_called()
        mocked_pebble_service.plan.assert_not_called()
        assert harness.charm.unit.status == BlockedStatus(
            "Requires a secure (HTTPS) public ingress. "
            "Either enable HTTPS on public ingress or set 'dev' config to true for local development."
        )

    def test_when_database_not_ready(
        self,
        harness: Harness,
        mocked_event: MagicMock,
        public_ingress_integration_data: None,
        login_ui_integration_data: None,
        peer_integration: int,
        mocked_pebble_service: MagicMock,
    ) -> None:
        with patch("charm.DatabaseRequires.is_resource_created", return_value=False):
            harness.charm._holistic_handler(mocked_event)

        mocked_pebble_service.update_config_file.assert_not_called()
        mocked_pebble_service.plan.assert_not_called()
        assert harness.charm.unit.status == WaitingStatus("Waiting for database creation")

    def test_when_migration_is_needed(
        self,
        harness: Harness,
        mocked_event: MagicMock,
        public_ingress_integration_data: None,
        login_ui_integration_data: None,
        peer_integration: int,
        mocked_pebble_service: MagicMock,
    ) -> None:
        with patch(
            "charm.HydraCharm.migration_needed", new_callable=PropertyMock, return_value=True
        ):
            harness.charm._holistic_handler(mocked_event)

        mocked_pebble_service.update_config_file.assert_not_called()
        mocked_pebble_service.plan.assert_not_called()
        assert harness.charm.unit.status == WaitingStatus(
            "Waiting for migration to run, try running the `run-migration` action"
        )

    def test_when_secrets_not_ready(
        self,
        harness: Harness,
        mocked_event: MagicMock,
        public_ingress_integration_data: None,
        login_ui_integration_data: None,
        peer_integration: int,
        mocked_pebble_service: MagicMock,
        mocked_secrets: MagicMock,
    ) -> None:
        mocked_secrets.is_ready = False

        harness.charm._holistic_handler(mocked_event)
        mocked_pebble_service.update_config_file.assert_not_called()
        mocked_pebble_service.plan.assert_not_called()
        assert harness.charm.unit.status == WaitingStatus("Waiting for secrets creation")

    def test_when_login_ui_not_ready(
        self,
        harness: Harness,
        mocked_event: MagicMock,
        public_ingress_integration_data: None,
        peer_integration: int,
        mocked_pebble_service: MagicMock,
        mocked_secrets: MagicMock,
        login_ui_integration: int,
    ) -> None:
        harness.charm._holistic_handler(mocked_event)

        mocked_pebble_service.update_config_file.assert_not_called()
        mocked_pebble_service.plan.assert_not_called()
        assert harness.charm.unit.status == WaitingStatus("Waiting for login UI to be ready")

    def test_when_pebble_plan_failed(
        self,
        harness: Harness,
        mocked_event: MagicMock,
        public_ingress_integration_data: None,
        login_ui_integration_data: None,
        peer_integration: int,
        mocked_pebble_service: MagicMock,
    ) -> None:
        with (
            patch("charm.ConfigFile.from_sources", return_value=ConfigFile("config")),
            patch("charm.PebbleService.plan", side_effect=PebbleServiceError),
        ):
            harness.charm._holistic_handler(mocked_event)

        mocked_pebble_service.update_config_file.assert_called_once()
        assert harness.charm.unit.status == BlockedStatus(
            f"Failed to restart the service, please check the {WORKLOAD_CONTAINER} logs"
        )

    def test_when_succeeds(
        self,
        harness: Harness,
        mocked_event: MagicMock,
        public_ingress_integration_data: None,
        login_ui_integration_data: None,
        peer_integration: int,
        mocked_pebble_service: MagicMock,
    ) -> None:
        with patch("charm.ConfigFile.from_sources", return_value=ConfigFile("config")):
            harness.charm._holistic_handler(mocked_event)

        mocked_pebble_service.update_config_file.assert_called_once()
        mocked_pebble_service.plan.assert_called_once()
        assert harness.charm.unit.status == ActiveStatus()
