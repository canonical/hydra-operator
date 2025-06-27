# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

from dataclasses import asdict
from unittest.mock import MagicMock, create_autospec, mock_open, patch

import pytest
from charms.data_platform_libs.v0.data_interfaces import DatabaseRequires
from charms.hydra.v0.hydra_token_hook import (
    HydraHookRequirer,
    ProviderData,
)
from charms.identity_platform_login_ui_operator.v0.login_ui_endpoints import (
    LoginUIEndpointsRequirer,
)
from charms.tempo_coordinator_k8s.v0.tracing import TracingEndpointRequirer
from charms.traefik_k8s.v0.traefik_route import TraefikRouteRequirer
from charms.traefik_k8s.v2.ingress import IngressPerAppRequirer
from ops.testing import Harness
from yarl import URL

from constants import ADMIN_PORT, POSTGRESQL_DSN_TEMPLATE, PUBLIC_PORT
from integrations import (
    DatabaseConfig,
    HydraHookData,
    InternalIngressData,
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


class TestHydraHookData:
    @pytest.fixture
    def mocked_data(self) -> ProviderData:
        return ProviderData(
            url="https://path/to/hook",
            auth_config_name="Authorization",
            auth_config_value="token",
            auth_config_in="header",
        )

    @pytest.fixture
    def mocked_requirer(self, mocked_data: ProviderData) -> MagicMock:
        s = create_autospec(HydraHookRequirer)
        s.consume_relation_data.return_value = mocked_data
        return s

    def test_to_service_configs(self, mocked_data: ProviderData) -> None:
        data = HydraHookData(
            is_ready=True,
            auth_enabled=True,
            url=mocked_data.url,
            auth_name=mocked_data.auth_config_name,
            auth_value=mocked_data.auth_config_value,
            auth_in=mocked_data.auth_config_in,
        )
        assert data.to_service_configs() == {
            "token_hook_url": mocked_data.url,
            "token_hook_auth_type": "api_key",
            "token_hook_auth_name": mocked_data.auth_config_name,
            "token_hook_auth_value": mocked_data.auth_config_value,
            "token_hook_auth_in": mocked_data.auth_config_in,
        }

    def test_to_service_configs_without_auth(self, mocked_data: ProviderData) -> None:
        data = HydraHookData(
            is_ready=True,
            auth_enabled=False,
            url=mocked_data.url,
        )
        assert data.to_service_configs() == {
            "token_hook_url": mocked_data.url,
        }

    def test_load_when_integration_ready(
        self, mocked_requirer: MagicMock, mocked_data: ProviderData
    ) -> None:
        mocked_requirer.ready.return_value = True

        actual = HydraHookData.load(mocked_requirer)
        assert actual == HydraHookData(
            is_ready=True,
            auth_enabled=True,
            url=mocked_data.url,
            auth_type="api_key",
            auth_name=mocked_data.auth_config_name,
            auth_value=mocked_data.auth_config_value,
            auth_in=mocked_data.auth_config_in,
        )

    def test_load_when_integration_ready_without_auth(
        self,
        mocked_requirer: MagicMock,
    ) -> None:
        mocked_requirer.ready.return_value = True
        data = ProviderData(url="https://path/to/hook")
        mocked_requirer.consume_relation_data.return_value = data

        actual = HydraHookData.load(mocked_requirer)
        assert actual == HydraHookData(
            is_ready=True,
            url=data.url,
        )

    def test_load_when_integration_not_ready(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.ready.return_value = False

        actual = HydraHookData.load(mocked_requirer)
        assert actual == HydraHookData()


class TestInternalIngressData:
    @pytest.fixture
    def mocked_requirer(self) -> MagicMock:
        mocked = create_autospec(TraefikRouteRequirer)
        mocked._charm = MagicMock()
        mocked._charm.model.name = "model"
        mocked._charm.app.name = "app"
        mocked.scheme = "http"
        return mocked

    @pytest.fixture
    def ingress_template(self) -> str:
        return (
            '{"model": "{{ model }}", '
            '"app": "{{ app }}", '
            '"public_port": {{ public_port }}, '
            '"admin_port": {{ admin_port }}, '
            '"external_host": "{{ external_host }}"}'
        )

    def test_load_with_external_host(
        self, mocked_requirer: MagicMock, ingress_template: str
    ) -> None:
        mocked_requirer.external_host = "external.hydra.com"

        with patch("builtins.open", mock_open(read_data=ingress_template)):
            actual = InternalIngressData.load(mocked_requirer)

        expected_ingress_config = {
            "model": "model",
            "app": "app",
            "public_port": PUBLIC_PORT,
            "admin_port": ADMIN_PORT,
            "external_host": "external.hydra.com",
        }
        assert actual == InternalIngressData(
            public_endpoint=URL("http://external.hydra.com/model-app"),
            admin_endpoint=URL("http://external.hydra.com/model-app"),
            config=expected_ingress_config,
        )

    def test_load_without_external_host(
        self, mocked_requirer: MagicMock, ingress_template: str
    ) -> None:
        mocked_requirer.external_host = ""

        with patch("builtins.open", mock_open(read_data=ingress_template)):
            actual = InternalIngressData.load(mocked_requirer)

        expected_ingress_config = {
            "model": "model",
            "app": "app",
            "public_port": PUBLIC_PORT,
            "admin_port": ADMIN_PORT,
            "external_host": "",
        }
        assert actual == InternalIngressData(
            public_endpoint=URL(f"http://app.model.svc.cluster.local:{PUBLIC_PORT}"),
            admin_endpoint=URL(f"http://app.model.svc.cluster.local:{ADMIN_PORT}"),
            config=expected_ingress_config,
        )
