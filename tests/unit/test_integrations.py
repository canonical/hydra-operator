# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

from dataclasses import asdict
from unittest.mock import MagicMock, create_autospec

import pytest
from charms.data_platform_libs.v0.data_interfaces import DatabaseRequires
from charms.identity_platform_login_ui_operator.v0.login_ui_endpoints import (
    LoginUIEndpointsRequirer,
)
from charms.tempo_k8s.v2.tracing import TracingEndpointRequirer
from charms.traefik_k8s.v2.ingress import IngressPerAppRequirer
from ops.testing import Harness
from yarl import URL

from constants import POSTGRESQL_DSN_TEMPLATE
from integrations import (
    DatabaseConfig,
    LoginUIEndpointData,
    PeerData,
    PublicIngressData,
    TracingData,
)


class TestPeerData:
    @pytest.fixture
    def peer_data(self, harness: Harness) -> PeerData:
        data = PeerData(harness.model)
        data["key"] = "val"
        return data

    def test_without_peer_integration(self, peer_data: PeerData) -> None:
        assert peer_data["key"] == {}

    def test_with_wrong_key(self, peer_integration: int, peer_data: PeerData) -> None:
        assert peer_data["wrong_key"] == {}

    def test_get(self, peer_integration: int, peer_data: PeerData) -> None:
        assert peer_data["key"] == "val"

    def test_pop_without_peer_integration(
        self, harness: Harness, peer_integration: int, peer_data: PeerData
    ) -> None:
        harness.remove_relation(peer_integration)
        assert peer_data.pop("key") == {}

    def test_pop_with_wrong_key(self, peer_integration: int, peer_data: PeerData) -> None:
        assert peer_data.pop("wrong_key") == {}
        assert peer_data["key"] == "val"

    def test_pop(self, peer_integration: int, peer_data: PeerData) -> None:
        assert peer_data.pop("key") == "val"
        assert peer_data["key"] == {}

    def test_keys(self, peer_integration: int, peer_data: PeerData) -> None:
        assert tuple(peer_data.keys()) == ("key",)

    def test_keys_without_peer_integration(self, peer_data: PeerData) -> None:
        assert not tuple(peer_data.keys())


class TestDatabaseConfig:
    @pytest.fixture
    def database_config(self) -> DatabaseConfig:
        return DatabaseConfig(
            username="username",
            password="password",
            endpoint="endpoint",
            database="database",
            migration_version="migration_version",
        )

    @pytest.fixture
    def mocked_requirer(self) -> MagicMock:
        return create_autospec(DatabaseRequires)

    def test_dsn(self, database_config: DatabaseConfig) -> None:
        expected = POSTGRESQL_DSN_TEMPLATE.substitute(
            username="username",
            password="password",
            endpoint="endpoint",
            database="database",
        )

        actual = database_config.dsn
        assert actual == expected

    def test_to_service_configs(self, database_config: DatabaseConfig) -> None:
        service_configs = database_config.to_service_configs()
        assert service_configs["dsn"] == database_config.dsn

    def test_load_with_integration(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.relations = [MagicMock(id=1)]
        mocked_requirer.database = "database"
        mocked_requirer.fetch_relation_data.return_value = {
            1: {"endpoints": "endpoint", "username": "username", "password": "password"}
        }

        actual = DatabaseConfig.load(mocked_requirer)
        assert actual == DatabaseConfig(
            username="username",
            password="password",
            endpoint="endpoint",
            database="database",
            migration_version="migration_version_1",
        )

    def test_load_without_integration(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.database = "database"
        mocked_requirer.relations = []

        actual = DatabaseConfig.load(mocked_requirer)
        assert actual == DatabaseConfig()


class TestTracingData:
    @pytest.fixture
    def mocked_requirer(self) -> MagicMock:
        return create_autospec(TracingEndpointRequirer)

    @pytest.mark.parametrize(
        "data, expected",
        [
            (TracingData(is_ready=False), {}),
            (
                TracingData(is_ready=True, http_endpoint="http_endpoint"),
                {
                    "TRACING_ENABLED": True,
                    "TRACING_PROVIDER": "otel",
                    "TRACING_PROVIDERS_OTLP_SERVER_URL": "http_endpoint",
                    "TRACING_PROVIDERS_OTLP_INSECURE": "true",
                    "TRACING_PROVIDERS_OTLP_SAMPLING_SAMPLING_RATIO": "1.0",
                },
            ),
        ],
    )
    def test_to_env_vars(self, data: TracingData, expected: dict) -> None:
        actual = data.to_env_vars()
        assert actual == expected

    def test_load_with_integration_ready(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.is_ready.return_value = True
        mocked_requirer.get_endpoint.return_value = "http://http_endpoint"

        actual = TracingData.load(mocked_requirer)
        assert actual == TracingData(is_ready=True, http_endpoint="http_endpoint")

    def test_load_without_integration_ready(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.is_ready.return_value = False

        actual = TracingData.load(mocked_requirer)
        assert actual == TracingData()


class TestLoginUIEndpointData:
    @pytest.fixture
    def endpoint_data(self) -> LoginUIEndpointData:
        return LoginUIEndpointData(
            consent_url="consent_url",
            device_verification_url="device_verification_url",
            oidc_error_url="oidc_error_url",
            login_url="login_url",
            post_device_done_url="post_device_done_url",
        )

    @pytest.fixture
    def mocked_requirer(self) -> MagicMock:
        return create_autospec(LoginUIEndpointsRequirer)

    def test_to_service_configs(self, endpoint_data: LoginUIEndpointData) -> None:
        actual = endpoint_data.to_service_configs()
        assert actual == asdict(endpoint_data)

    def test_load(self, endpoint_data: LoginUIEndpointData, mocked_requirer: MagicMock) -> None:
        mocked_requirer.get_login_ui_endpoints.return_value = {
            "consent_url": "consent_url",
            "device_verification_url": "device_verification_url",
            "error_url": "error_url",
            "login_url": "login_url",
            "oidc_error_url": "oidc_error_url",
            "post_device_done_url": "post_device_done_url",
            "recovery_url": "recovery_url",
            "settings_url": "settings_url",
        }

        actual = LoginUIEndpointData.load(mocked_requirer)
        assert actual == endpoint_data

    def test_load_with_failure(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.get_login_ui_endpoints.side_effect = Exception

        actual = LoginUIEndpointData.load(mocked_requirer)
        assert actual == LoginUIEndpointData()


class TestPublicIngressData:
    @pytest.fixture
    def mocked_requirer(self) -> MagicMock:
        return create_autospec(IngressPerAppRequirer)

    def test_to_service_configs(self) -> None:
        data = PublicIngressData(url=URL("https://hydra.ory.com"))
        assert data.to_service_configs() == {"public_url": "https://hydra.ory.com"}

    def test_load_with_integration_ready(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.is_ready.return_value = True
        mocked_requirer.url = "https://hydra.ory.com"

        actual = PublicIngressData.load(mocked_requirer)
        assert actual == PublicIngressData(url=URL("https://hydra.ory.com"))

    def test_load_without_integration_ready(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.is_ready.return_value = False

        actual = PublicIngressData.load(mocked_requirer)
        assert actual == PublicIngressData()
