# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest
from ops.testing import ActionFailed, Context, PeerRelation
from pytest_mock import MockerFixture
from unit.conftest import create_state

from cli import OAuthClient
from exceptions import CommandExecError, MigrationError
from integrations import DatabaseConfig


class TestRunMigrationAction:
    @pytest.fixture(autouse=True)
    def mocked_database_config(self, mocker: MockerFixture) -> DatabaseConfig:
        mocked = mocker.patch(
            "charm.DatabaseConfig.load",
            return_value=DatabaseConfig(migration_version="migration_version_0"),
        )
        return mocked.return_value

    @pytest.fixture
    def mocked_cli(self, mocker: MockerFixture) -> MagicMock:
        return mocker.patch("charm.CommandLine.migrate")

    def test_when_not_leader_unit(
        self,
        context: Context,
        mocked_cli: MagicMock,
    ) -> None:
        state = create_state(leader=False)
        with pytest.raises(
            ActionFailed, match="Only the leader unit can run the database migration"
        ):
            context.run(context.on.action("run-migration"), state)

        mocked_cli.assert_not_called()

    def test_when_container_not_connected(
        self,
        context: Context,
    ) -> None:
        state = create_state(leader=True, can_connect=False)
        with pytest.raises(ActionFailed, match="Container is not connected yet"):
            context.run(context.on.action("run-migration"), state)

    def test_when_peer_integration_not_exists(
        self,
        context: Context,
        mocked_cli: MagicMock,
    ) -> None:
        state = create_state(leader=True, relations=[])
        with pytest.raises(ActionFailed) as excinfo:
            context.run(context.on.action("run-migration"), state)

        assert "Peer integration is not ready yet" in excinfo.value.message
        mocked_cli.assert_not_called()

    def test_when_commandline_failed(
        self,
        context: Context,
        peer_relation_ready: PeerRelation,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.side_effect = MigrationError("failed")
        state = create_state(leader=True, relations=[peer_relation_ready])

        with pytest.raises(ActionFailed) as excinfo:
            context.run(context.on.action("run-migration"), state)

        assert "Database migration failed" in excinfo.value.message

    def test_when_action_succeeds(
        self,
        context: Context,
        peer_relation_ready: PeerRelation,
        mocked_cli: MagicMock,
        hydra_workload_version: str,
    ) -> None:
        state = create_state(leader=True, relations=[peer_relation_ready])

        out = context.run(context.on.action("run-migration"), state)

        mocked_cli.assert_called_once()
        assert out.get_relation(peer_relation_ready.id).local_app_data[
            "migration_version_0"
        ] == json.dumps(hydra_workload_version)


class TestCreateOAuthClientAction:
    @pytest.fixture
    def mocked_cli(self, mocker: MockerFixture, mocked_oauth_client_config: dict) -> MagicMock:
        return mocker.patch(
            "charm.CommandLine.create_oauth_client",
            return_value=OAuthClient(**mocked_oauth_client_config),
        )

    def test_when_hydra_service_not_ready(
        self,
        context: Context,
        mocked_cli: MagicMock,
    ) -> None:
        state = create_state(hydra_is_running=False)
        with pytest.raises(
            ActionFailed,
            match="Service is not ready. Please re-run the action when the charm is active",
        ):
            context.run(
                context.on.action(
                    "create-oauth-client",
                    {
                        "redirect-uris": ["https://example.oidc.client/callback"],
                        "token-endpoint-auth-method": "client_secret_basic",
                    },
                ),
                state,
            )

        mocked_cli.assert_not_called()

    def test_when_commandline_failed(
        self,
        context: Context,
    ) -> None:
        with patch("charm.CommandLine.create_oauth_client", return_value=None):
            state = create_state()
            with pytest.raises(
                ActionFailed,
                match="Failed to create the OAuth client. Please check the juju logs",
            ):
                context.run(
                    context.on.action(
                        "create-oauth-client",
                        {
                            "redirect-uris": ["https://example.oidc.client/callback"],
                            "token-endpoint-auth-method": "client_secret_basic",
                        },
                    ),
                    state,
                )

    def test_when_action_succeeds(
        self,
        context: Context,
        mocked_cli: MagicMock,
    ) -> None:
        redirect_uris = ["https://example.oidc.client/callback"]
        state = create_state()
        context.run(
            context.on.action(
                "create-oauth-client",
                {
                    "redirect-uris": redirect_uris,
                    "token-endpoint-auth-method": "client_secret_basic",
                },
            ),
            state,
        )

        mocked_cli.assert_called_once()
        assert context.action_results
        assert context.action_results["redirect-uris"] == redirect_uris


class TestGetOAuthClientInfoAction:
    @pytest.fixture
    def mocked_cli(self, mocker: MockerFixture, mocked_oauth_client_config: dict) -> MagicMock:
        return mocker.patch(
            "charm.CommandLine.get_oauth_client",
            return_value=OAuthClient(**mocked_oauth_client_config),
        )

    def test_when_hydra_service_not_ready(
        self,
        context: Context,
        mocked_cli: MagicMock,
    ) -> None:
        state = create_state(hydra_is_running=False)
        with pytest.raises(
            ActionFailed,
            match="Service is not ready. Please re-run the action when the charm is active",
        ):
            context.run(
                context.on.action("get-oauth-client-info", {"client-id": "client_id"}), state
            )
        mocked_cli.assert_not_called()

    def test_when_commandline_failed(
        self,
        context: Context,
    ) -> None:
        with patch("charm.CommandLine.get_oauth_client", return_value=None):
            state = create_state()
            with pytest.raises(
                ActionFailed, match="Failed to get the OAuth client. Please check the juju logs"
            ):
                context.run(
                    context.on.action("get-oauth-client-info", {"client-id": "client_id"}), state
                )

    def test_when_action_succeeds(
        self,
        context: Context,
        mocked_cli: MagicMock,
        mocked_oauth_client_config: dict,
    ) -> None:
        state = create_state()
        context.run(context.on.action("get-oauth-client-info", {"client-id": "client_id"}), state)
        mocked_cli.assert_called_once()
        expected = OAuthClient(**mocked_oauth_client_config).model_dump(
            by_alias=True, exclude_none=True
        )
        assert context.action_results == expected


class TestUpdateOAuthClientAction:
    @pytest.fixture(autouse=True)
    def mocked_oauth_client(
        self, mocker: MockerFixture, mocked_oauth_client_config: dict
    ) -> MagicMock:
        return mocker.patch(
            "charm.CommandLine.get_oauth_client",
            return_value=OAuthClient(
                **mocked_oauth_client_config,
                **{"client-id": "client_id"},
            ),
        )

    @pytest.fixture
    def mocked_cli(self, mocker: MockerFixture, mocked_oauth_client_config: dict) -> MagicMock:
        return mocker.patch(
            "charm.CommandLine.update_oauth_client",
            return_value=OAuthClient(**mocked_oauth_client_config),
        )

    def test_when_hydra_service_not_ready(
        self,
        context: Context,
        mocked_cli: MagicMock,
    ) -> None:
        state = create_state(hydra_is_running=False)
        with pytest.raises(
            ActionFailed,
            match="Service is not ready. Please re-run the action when the charm is active",
        ):
            context.run(
                context.on.action("update-oauth-client", {"client-id": "client_id"}), state
            )
        mocked_cli.assert_not_called()

    def test_when_oauth_client_not_exists(
        self,
        context: Context,
        mocked_cli: MagicMock,
    ) -> None:
        with patch("charm.CommandLine.get_oauth_client", return_value=None):
            state = create_state()
            with pytest.raises(ActionFailed, match="Failed to get the OAuth client"):
                context.run(
                    context.on.action("update-oauth-client", {"client-id": "client_id"}), state
                )

        mocked_cli.assert_not_called()

    def test_when_oauth_client_managed_by_integration(
        self,
        context: Context,
        mocked_cli: MagicMock,
    ) -> None:
        with patch(
            "charm.CommandLine.get_oauth_client",
            return_value=OAuthClient(metadata={"integration-id": "id"}),
        ):
            state = create_state()
            with pytest.raises(
                ActionFailed,
                match="Cannot update the OAuth client client_id because it's managed by an `oauth` integration",
            ):
                context.run(
                    context.on.action("update-oauth-client", {"client-id": "client_id"}), state
                )

        mocked_cli.assert_not_called()

    def test_when_commandline_failed(
        self,
        context: Context,
    ) -> None:
        with patch("charm.CommandLine.update_oauth_client", return_value=None):
            state = create_state()
            with pytest.raises(
                ActionFailed,
                match="Failed to update the OAuth client client_id. Please check the juju logs",
            ):
                context.run(
                    context.on.action("update-oauth-client", {"client-id": "client_id"}), state
                )

    def test_when_action_succeeds(
        self,
        context: Context,
        mocked_cli: MagicMock,
        mocked_oauth_client_config: dict,
    ) -> None:
        state = create_state()
        context.run(
            context.on.action(
                "update-oauth-client",
                {
                    "client-id": "client_id",
                    "redirect-uris": ["https://example.ory.com"],
                    "contacts": ["test@canonical.com", "me@me.com"],
                    "client-uri": "https://example.com",
                    "metadata": "foo=bar bar=foo",
                    "name": "test-client",
                },
            ),
            state,
        )

        mocked_cli.assert_called_once()
        action_call_arg: OAuthClient = mocked_cli.call_args[0][0]
        assert action_call_arg.redirect_uris == ["https://example.ory.com"]
        assert action_call_arg.contacts == ["test@canonical.com", "me@me.com"]
        assert action_call_arg.client_uri == "https://example.com"
        assert action_call_arg.metadata == {"foo": "bar", "bar": "foo"}
        assert action_call_arg.name == "test-client"

        assert context.action_results == OAuthClient(**mocked_oauth_client_config).model_dump(
            by_alias=True, exclude_none=True
        )


class TestDeleteOAuthClientAction:
    @pytest.fixture(autouse=True)
    def mocked_oauth_client(
        self, mocker: MockerFixture, mocked_oauth_client_config: dict
    ) -> MagicMock:
        return mocker.patch(
            "charm.CommandLine.get_oauth_client",
            return_value=OAuthClient(
                **mocked_oauth_client_config,
                **{"client-id": "client_id"},
            ),
        )

    @pytest.fixture
    def mocked_cli(self, mocker: MockerFixture) -> MagicMock:
        return mocker.patch("charm.CommandLine.delete_oauth_client", return_value="client_id")

    def test_when_hydra_service_not_ready(
        self,
        context: Context,
        mocked_cli: MagicMock,
    ) -> None:
        state = create_state(hydra_is_running=False)
        with pytest.raises(ActionFailed) as excinfo:
            context.run(
                context.on.action("delete-oauth-client", {"client-id": "client_id"}), state
            )
        assert (
            "Service is not ready. Please re-run the action when the charm is active"
            in excinfo.value.message
        )
        mocked_cli.assert_not_called()

    def test_when_oauth_client_not_exists(
        self,
        context: Context,
        mocked_cli: MagicMock,
    ) -> None:
        with patch("charm.CommandLine.get_oauth_client", return_value=None):
            state = create_state()
            with pytest.raises(ActionFailed) as excinfo:
                context.run(
                    context.on.action("delete-oauth-client", {"client-id": "client_id"}), state
                )
            assert "Failed to get the OAuth client" in excinfo.value.message

        mocked_cli.assert_not_called()

    def test_when_oauth_client_managed_by_integration(
        self,
        context: Context,
        mocked_cli: MagicMock,
    ) -> None:
        with patch(
            "charm.CommandLine.get_oauth_client",
            return_value=OAuthClient(metadata={"integration-id": "id"}),
        ):
            state = create_state()
            with pytest.raises(ActionFailed) as excinfo:
                context.run(
                    context.on.action("delete-oauth-client", {"client-id": "client_id"}), state
                )
            assert (
                "Cannot delete the OAuth client client_id because it's managed by an `oauth` integration"
                in excinfo.value.message
            )

        mocked_cli.assert_not_called()

    def test_when_commandline_failed(
        self,
        context: Context,
    ) -> None:
        with patch("charm.CommandLine.delete_oauth_client", return_value=None):
            state = create_state()
            with pytest.raises(ActionFailed) as excinfo:
                context.run(
                    context.on.action("delete-oauth-client", {"client-id": "client_id"}), state
                )
            assert (
                "Failed to delete the OAuth client client_id. Please check the juju logs"
                in excinfo.value.message
            )

    def test_when_action_succeeds(
        self,
        context: Context,
        mocked_cli: MagicMock,
    ) -> None:
        state = create_state()
        context.run(context.on.action("delete-oauth-client", {"client-id": "client_id"}), state)

        mocked_cli.assert_called_once_with("client_id")
        assert context.action_results == {"client-id": "client_id"}


class TestListOAuthClientsAction:
    @pytest.fixture
    def mocked_cli(self, mocker: MockerFixture, mocked_oauth_client_config: dict) -> MagicMock:
        return mocker.patch(
            "charm.CommandLine.list_oauth_clients",
            return_value=[OAuthClient(**mocked_oauth_client_config, **{"client-id": "client_id"})],
        )

    def test_when_hydra_service_not_ready(
        self,
        context: Context,
        mocked_cli: MagicMock,
    ) -> None:
        state = create_state(hydra_is_running=False)
        with pytest.raises(ActionFailed) as excinfo:
            context.run(context.on.action("list-oauth-clients"), state)
        assert (
            "Service is not ready. Please re-run the action when the charm is active"
            in excinfo.value.message
        )
        mocked_cli.assert_not_called()

    def test_when_commandline_failed(
        self,
        context: Context,
    ) -> None:
        with patch("charm.CommandLine.list_oauth_clients", return_value=[]):
            state = create_state()
            with pytest.raises(ActionFailed) as excinfo:
                context.run(context.on.action("list-oauth-clients"), state)
            assert (
                "Failed to list OAuth clients. Please check the juju logs" in excinfo.value.message
            )

    def test_when_action_succeeds(
        self,
        context: Context,
        mocked_cli: MagicMock,
    ) -> None:
        state = create_state()
        context.run(context.on.action("list-oauth-clients"), state)
        mocked_cli.assert_called_once()


class TestRevokeOAuthClientAccessTokenAction:
    @pytest.fixture
    def mocked_cli(self, mocker: MockerFixture) -> MagicMock:
        return mocker.patch(
            "charm.CommandLine.delete_oauth_client_access_tokens",
            return_value="client_id",
        )

    def test_when_hydra_service_not_ready(
        self,
        context: Context,
        mocked_cli: MagicMock,
    ) -> None:
        state = create_state(hydra_is_running=False)
        with pytest.raises(ActionFailed) as excinfo:
            context.run(
                context.on.action("revoke-oauth-client-access-tokens", {"client-id": "client_id"}),
                state,
            )
        assert (
            "Service is not ready. Please re-run the action when the charm is active"
            in excinfo.value.message
        )
        mocked_cli.assert_not_called()

    def test_when_commandline_failed(
        self,
        context: Context,
    ) -> None:
        with patch("charm.CommandLine.delete_oauth_client_access_tokens", return_value=None):
            state = create_state()
            with pytest.raises(ActionFailed) as excinfo:
                context.run(
                    context.on.action(
                        "revoke-oauth-client-access-tokens", {"client-id": "client_id"}
                    ),
                    state,
                )
            assert (
                "Failed to revoke the access tokens of the OAuth client client_id. Please check juju logs"
                in excinfo.value.message
            )

    def test_when_action_succeeds(
        self,
        context: Context,
        mocked_cli: MagicMock,
    ) -> None:
        state = create_state()
        context.run(
            context.on.action("revoke-oauth-client-access-tokens", {"client-id": "client_id"}),
            state,
        )

        mocked_cli.assert_called_once_with("client_id")


class TestRotateKeyAction:
    @pytest.fixture
    def mocked_cli(self, mocker: MockerFixture) -> MagicMock:
        return mocker.patch(
            "charm.CommandLine.create_jwk",
            return_value="key_id",
        )

    def test_when_hydra_service_not_ready(
        self,
        context: Context,
        mocked_cli: MagicMock,
    ) -> None:
        state = create_state(hydra_is_running=False)
        with pytest.raises(ActionFailed) as excinfo:
            context.run(context.on.action("rotate-key", {"algorithm": "RS256"}), state)
        assert (
            "Service is not ready. Please re-run the action when the charm is active"
            in excinfo.value.message
        )
        mocked_cli.assert_not_called()

    def test_when_commandline_failed(
        self,
        context: Context,
    ) -> None:
        with patch("charm.CommandLine.create_jwk", return_value=None):
            state = create_state()
            with pytest.raises(ActionFailed) as excinfo:
                context.run(context.on.action("rotate-key", {"algorithm": "RS256"}), state)
            assert "Failed to rotate the JWK. Please check the juju logs" in excinfo.value.message

    def test_when_action_succeeds(
        self,
        context: Context,
        mocked_cli: MagicMock,
    ) -> None:
        state = create_state()
        context.run(context.on.action("rotate-key", {"algorithm": "RS256"}), state)

        mocked_cli.assert_called_once_with(algorithm="RS256")


class TestReconcileOauthClientsAction:
    @pytest.fixture
    def mocked_cli(self, mocker: MockerFixture) -> MagicMock:
        return mocker.patch(
            "charm.CommandLine.delete_oauth_client",
            return_value="client_id",
        )

    def test_when_not_leader(
        self,
        context: Context,
        mocked_cli: MagicMock,
    ) -> None:
        state = create_state(leader=False)
        with pytest.raises(ActionFailed) as excinfo:
            context.run(context.on.action("reconcile-oauth-clients"), state)
        assert "You need to run this action from the leader unit" in excinfo.value.message
        mocked_cli.assert_not_called()

    def test_when_hydra_service_not_ready(
        self,
        context: Context,
        mocked_cli: MagicMock,
    ) -> None:
        state = create_state(leader=True, hydra_is_running=False)
        with pytest.raises(ActionFailed) as excinfo:
            context.run(context.on.action("reconcile-oauth-clients"), state)
        assert (
            "Service is not ready. Please re-run the action when the charm is active"
            in excinfo.value.message
        )
        mocked_cli.assert_not_called()

    def test_when_commandline_failed(
        self,
        context: Context,
        peer_relation_ready: PeerRelation,
    ) -> None:
        data = {
            "oauth_1": json.dumps({"client_id": "client_1"}),
        }

        with patch(
            "charm.CommandLine.delete_oauth_client",
            side_effect=CommandExecError([], 1, "", "error"),
        ):
            state = create_state(
                leader=True,
                relations=[replace(peer_relation_ready, local_app_data=data)],
            )
            # Action should NOT fail, it logs error and continues
            context.run(context.on.action("reconcile-oauth-clients"), state)

    def test_when_action_succeeds(
        self,
        context: Context,
        mocked_cli: MagicMock,
        peer_relation_ready: PeerRelation,
    ) -> None:
        data = {
            "oauth_1": json.dumps({"client_id": "client_id"}),
            "oauth_2": json.dumps({"client_id": "client_id"}),
            "oauth_3": json.dumps({"client_id": "client_id"}),
        }
        state = create_state(
            leader=True,
            relations=[replace(peer_relation_ready, local_app_data=data)],
        )

        context.run(context.on.action("reconcile-oauth-clients"), state)

        assert mocked_cli.call_count == 3
