# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from unittest.mock import MagicMock, patch

import pytest
from ops.testing import ActionFailed, Harness
from pytest_mock import MockerFixture

from cli import OAuthClient
from exceptions import MigrationError
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

    def test_when_hydra_service_not_ready(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        mocked_cli: MagicMock,
        peer_integration: int,
    ) -> None:
        mocked_workload_service.is_running = False
        try:
            harness.run_action("run-migration")
        except ActionFailed as err:
            assert (
                "Service is not ready. Please re-run the action when the charm is active"
                in err.message
            )

        mocked_cli.assert_not_called()

    def test_when_peer_integration_not_exists(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_workload_service.is_running = True
        try:
            harness.run_action("run-migration")
        except ActionFailed as err:
            assert "Peer integration is not ready yet" in err.message

        mocked_cli.assert_not_called()

    def test_when_commandline_failed(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        mocked_cli: MagicMock,
        peer_integration: int,
    ) -> None:
        mocked_workload_service.is_running = True
        with patch("charm.CommandLine.migrate", side_effect=MigrationError):
            try:
                harness.run_action("run-migration")
            except ActionFailed as err:
                assert "Database migration failed" in err.message

        assert not harness.charm.peer_data["migration_version_0"]

    def test_when_action_succeeds(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        mocked_workload_service_version: MagicMock,
        mocked_cli: MagicMock,
        peer_integration: int,
    ) -> None:
        harness.set_leader(True)
        mocked_workload_service.version = "1.0.0"
        mocked_workload_service.is_running = True

        harness.run_action("run-migration")

        mocked_cli.assert_called_once()
        assert harness.charm.peer_data["migration_version_0"] == "1.0.0"


class TestCreateOAuthClientAction:
    @pytest.fixture
    def mocked_cli(self, mocker: MockerFixture, mocked_oauth_client_config: dict) -> MagicMock:
        return mocker.patch(
            "charm.CommandLine.create_oauth_client",
            return_value=OAuthClient(**mocked_oauth_client_config),
        )

    def test_when_hydra_service_not_ready(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_workload_service.is_running = False
        try:
            harness.run_action(
                "create-oauth-client",
                {
                    "redirect-uris": ["https://example.oidc.client/callback"],
                    "token-endpoint-auth-method": "client_secret_basic",
                },
            )
        except ActionFailed as err:
            assert (
                "Service is not ready. Please re-run the action when the charm is active"
                in err.message
            )

        mocked_cli.assert_not_called()

    def test_when_commandline_failed(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
    ) -> None:
        mocked_workload_service.is_running = True
        with patch("charm.CommandLine.create_oauth_client", return_value=None):
            try:
                harness.run_action(
                    "create-oauth-client",
                    {
                        "redirect-uris": ["https://example.oidc.client/callback"],
                        "token-endpoint-auth-method": "client_secret_basic",
                    },
                )
            except ActionFailed as err:
                assert (
                    "Failed to create the OAuth client. Please check the juju logs" in err.message
                )

    def test_when_action_succeeds(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        mocked_cli: MagicMock,
        mocked_oauth_client_config: dict,
    ) -> None:
        mocked_workload_service.is_running = True
        output = harness.run_action(
            "create-oauth-client",
            {
                "redirect-uris": ["https://example.oidc.client/callback"],
                "token-endpoint-auth-method": "client_secret_basic",
            },
        )

        mocked_cli.assert_called_once()
        assert output.results["redirect-uris"] == [mocked_oauth_client_config["redirect_uri"]]
        assert (
            output.results["token-endpoint-auth-method"]
            == mocked_oauth_client_config["token_endpoint_auth_method"]
        )


class TestGetOAuthClientInfoAction:
    @pytest.fixture
    def mocked_cli(self, mocker: MockerFixture, mocked_oauth_client_config: dict) -> MagicMock:
        return mocker.patch(
            "charm.CommandLine.get_oauth_client",
            return_value=OAuthClient(**mocked_oauth_client_config),
        )

    def test_when_hydra_service_not_ready(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_workload_service.is_running = False
        try:
            harness.run_action("get-oauth-client-info", {"client-id": "client_id"})
        except ActionFailed as err:
            assert (
                "Service is not ready. Please re-run the action when the charm is active"
                in err.message
            )

        mocked_cli.assert_not_called()

    def test_when_commandline_failed(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
    ) -> None:
        mocked_workload_service.is_running = True
        try:
            harness.run_action("get-oauth-client-info", {"client-id": "client_id"})
        except ActionFailed as err:
            assert "Failed to get the OAuth client. Please check the juju logs" in err.message

    def test_when_action_succeeds(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        mocked_cli: MagicMock,
        mocked_oauth_client_config: dict,
    ) -> None:
        mocked_workload_service.is_running = True

        output = harness.run_action("get-oauth-client-info", {"client-id": "client_id"})
        mocked_cli.assert_called_once()
        assert output.results["redirect-uris"] == [mocked_oauth_client_config["redirect_uri"]]


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
        harness: Harness,
        mocked_workload_service: MagicMock,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_workload_service.is_running = False

        try:
            harness.run_action("update-oauth-client", {"client-id": "client_id"})
        except ActionFailed as err:
            assert (
                "Service is not ready. Please re-run the action when the charm is active"
                in err.message
            )

        mocked_cli.assert_not_called()

    def test_when_oauth_client_not_exists(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_workload_service.is_running = True

        with patch("charm.CommandLine.get_oauth_client", return_value=None):
            try:
                harness.run_action("update-oauth-client", {"client-id": "client_id"})
            except ActionFailed as err:
                assert "Failed to get the OAuth client" in err.message

        mocked_cli.assert_not_called()

    def test_when_oauth_client_managed_by_integration(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_workload_service.is_running = True

        with patch(
            "charm.CommandLine.get_oauth_client",
            return_value=OAuthClient(metadata={"integration-id": "id"}),
        ):
            try:
                harness.run_action("update-oauth-client", {"client-id": "client_id"})
            except ActionFailed as err:
                assert (
                    "Cannot update the OAuth client client_id because it's managed by an `oauth` integration"
                    in err.message
                )

        mocked_cli.assert_not_called()

    def test_when_commandline_failed(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
    ) -> None:
        mocked_workload_service.is_running = True

        with patch("charm.CommandLine.update_oauth_client", return_value=None):
            try:
                harness.run_action("update-oauth-client", {"client-id": "client_id"})
            except ActionFailed as err:
                assert (
                    "Failed to update the OAuth client client_id. Please check the juju logs"
                    in err.message
                )

    def test_when_action_succeeds(
        self, harness: Harness, mocked_workload_service: MagicMock, mocked_cli: MagicMock
    ) -> None:
        mocked_workload_service.is_running = True

        output = harness.run_action(
            "update-oauth-client",
            {
                "client-id": "client_id",
                "redirect-uris": ["https://example.ory.com"],
                "contacts": ["test@canonical.com", "me@me.com"],
                "client-uri": "https://example.com",
                "metadata": "foo=bar,bar=foo",
                "name": "test-client",
            },
        )
        assert "Successfully updated the OAuth client client_id" in output.logs

        mocked_cli.assert_called_once()
        action_call_arg: OAuthClient = mocked_cli.call_args[0][0]
        assert action_call_arg.redirect_uris == ["https://example.ory.com"]
        assert action_call_arg.contacts == ["test@canonical.com", "me@me.com"]
        assert action_call_arg.client_uri == "https://example.com"
        assert action_call_arg.metadata == {"foo": "bar", "bar": "foo"}
        assert action_call_arg.name == "test-client"


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
        harness: Harness,
        mocked_workload_service: MagicMock,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_workload_service.is_running = False

        try:
            harness.run_action("delete-oauth-client", {"client-id": "client_id"})
        except ActionFailed as err:
            assert (
                "Service is not ready. Please re-run the action when the charm is active"
                in err.message
            )

        mocked_cli.assert_not_called()

    def test_when_oauth_client_not_exists(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_workload_service.is_running = True

        with patch("charm.CommandLine.get_oauth_client", return_value=None):
            try:
                harness.run_action("delete-oauth-client", {"client-id": "client_id"})
            except ActionFailed as err:
                assert "Failed to get the OAuth client" in err.message

        mocked_cli.assert_not_called()

    def test_when_oauth_client_managed_by_integration(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_workload_service.is_running = True

        with patch(
            "charm.CommandLine.get_oauth_client",
            return_value=OAuthClient(metadata={"integration-id": "id"}),
        ):
            try:
                harness.run_action("delete-oauth-client", {"client-id": "client_id"})
            except ActionFailed as err:
                assert (
                    "Cannot delete the OAuth client client_id because it's managed by an `oauth` integration"
                    in err.message
                )

        mocked_cli.assert_not_called()

    def test_when_commandline_failed(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
    ) -> None:
        mocked_workload_service.is_running = True

        with patch("charm.CommandLine.delete_oauth_client", return_value=None):
            try:
                harness.run_action("delete-oauth-client", {"client-id": "client_id"})
            except ActionFailed as err:
                assert (
                    "Failed to delete the OAuth client client_id. Please check the juju logs"
                    in err.message
                )

    def test_when_action_succeeds(
        self, harness: Harness, mocked_workload_service: MagicMock, mocked_cli: MagicMock
    ) -> None:
        mocked_workload_service.is_running = True

        output = harness.run_action("delete-oauth-client", {"client-id": "client_id"})
        assert "Successfully deleted the OAuth client client_id" in output.logs

        mocked_cli.assert_called_once_with("client_id")
        assert output.results == {"client-id": "client_id"}


class TestListOAuthClientsAction:
    @pytest.fixture
    def mocked_cli(self, mocker: MockerFixture, mocked_oauth_client_config: dict) -> MagicMock:
        return mocker.patch(
            "charm.CommandLine.list_oauth_clients",
            return_value=[OAuthClient(**mocked_oauth_client_config, **{"client-id": "client_id"})],
        )

    def test_when_hydra_service_not_ready(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_workload_service.is_running = False

        try:
            harness.run_action("list-oauth-clients")
        except ActionFailed as err:
            assert (
                "Service is not ready. Please re-run the action when the charm is active"
                in err.message
            )

        mocked_cli.assert_not_called()

    def test_when_commandline_failed(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
    ) -> None:
        mocked_workload_service.is_running = True

        try:
            harness.run_action("list-oauth-clients")
        except ActionFailed as err:
            assert "Failed to list OAuth clients. Please check the juju logs" in err.message

    def test_when_action_succeeds(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_workload_service.is_running = True

        output = harness.run_action("list-oauth-clients")
        mocked_cli.assert_called_once()
        assert output.results == {"1": "client_id"}


class TestRevokeOAuthClientAccessTokenAction:
    @pytest.fixture
    def mocked_cli(self, mocker: MockerFixture) -> MagicMock:
        return mocker.patch(
            "charm.CommandLine.delete_oauth_client_access_tokens",
            return_value="client_id",
        )

    def test_when_hydra_service_not_ready(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_workload_service.is_running = False

        try:
            harness.run_action("revoke-oauth-client-access-tokens", {"client-id": "client_id"})
        except ActionFailed as err:
            assert (
                "Service is not ready. Please re-run the action when the charm is active"
                in err.message
            )

        mocked_cli.assert_not_called()

    def test_when_commandline_failed(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
    ) -> None:
        mocked_workload_service.is_running = True

        try:
            harness.run_action("revoke-oauth-client-access-tokens", {"client-id": "client_id"})
        except ActionFailed as err:
            assert (
                "Failed to revoke the access tokens of the OAuth client client_id. Please check juju logs"
                in err.message
            )

    def test_when_action_succeeds(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_workload_service.is_running = True

        output = harness.run_action(
            "revoke-oauth-client-access-tokens", {"client-id": "client_id"}
        )

        mocked_cli.assert_called_once_with("client_id")
        assert (
            "Successfully revoked the access tokens of the OAuth client client_id" in output.logs
        )
        assert output.results == {"client-id": "client_id"}


class TestRotateKeyAction:
    @pytest.fixture
    def mocked_cli(self, mocker: MockerFixture) -> MagicMock:
        return mocker.patch(
            "charm.CommandLine.create_jwk",
            return_value="key_id",
        )

    def test_when_hydra_service_not_ready(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_workload_service.is_running = False

        try:
            harness.run_action("rotate-key", {"algorithm": "RS256"})
        except ActionFailed as err:
            assert (
                "Service is not ready. Please re-run the action when the charm is active"
                in err.message
            )

        mocked_cli.assert_not_called()

    def test_when_commandline_failed(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
    ) -> None:
        mocked_workload_service.is_running = True

        with patch("charm.CommandLine.create_jwk", return_value=None):
            try:
                harness.run_action("rotate-key", {"algorithm": "RS256"})
            except ActionFailed as err:
                assert "Failed to rotate the JWK. Please check the juju logs" in err.message

    def test_when_action_succeeds(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_workload_service.is_running = True

        output = harness.run_action("rotate-key", {"algorithm": "RS256"})

        mocked_cli.assert_called_once_with(algorithm="RS256")
        assert "Successfully rotated the JWK" in output.logs
        assert output.results == {"new-key-id": "key_id"}


class TestReconcileOauthClientsAction:
    @pytest.fixture
    def mocked_cli(self, mocker: MockerFixture) -> MagicMock:
        return mocker.patch(
            "charm.CommandLine.delete_oauth_client",
            return_value="client_id",
        )

    def test_when_not_leader(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_workload_service.is_running = False

        try:
            harness.run_action("reconcile-oauth-clients")
        except ActionFailed as err:
            assert "You need to run this action from the leader unit" in err.message

        mocked_cli.assert_not_called()

    def test_when_hydra_service_not_ready(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        mocked_cli: MagicMock,
    ) -> None:
        harness.set_leader(True)
        mocked_workload_service.is_running = False

        try:
            harness.run_action("reconcile-oauth-clients")
        except ActionFailed as err:
            assert (
                "Service is not ready. Please re-run the action when the charm is active"
                in err.message
            )

        mocked_cli.assert_not_called()

    def test_when_commandline_failed(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
    ) -> None:
        harness.set_leader(True)
        mocked_workload_service.is_running = True

        with patch("charm.CommandLine.create_jwk", return_value=None):
            try:
                harness.run_action("reconcile-oauth-clients")
            except ActionFailed as err:
                assert "Failed to rotate the JWK. Please check the juju logs" in err.message

    def test_when_action_succeeds(
        self,
        harness: Harness,
        mocked_workload_service: MagicMock,
        mocked_cli: MagicMock,
        peer_integration: int,
    ) -> None:
        harness.set_leader(True)
        mocked_workload_service.is_running = True
        harness.update_relation_data(
            peer_integration,
            "hydra",
            {
                "oauth_1": json.dumps({"client_id": "client_id"}),
                "oauth_2": json.dumps({"client_id": "client_id"}),
                "oauth_3": json.dumps({"client_id": "client_id"}),
            },
        )

        output = harness.run_action("reconcile-oauth-clients")

        assert mocked_cli.call_count == 3
        assert "Successfully deleted 3 clients" in output.logs
