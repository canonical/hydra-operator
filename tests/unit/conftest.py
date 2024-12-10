# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Generator
from unittest.mock import MagicMock, PropertyMock, create_autospec

import pytest
from ops import Container, EventBase, Unit
from ops.testing import Harness
from pytest_mock import MockerFixture
from yarl import URL

from charm import HydraCharm
from constants import (
    DATABASE_INTEGRATION_NAME,
    OAUTH_INTEGRATION_NAME,
    PEER_INTEGRATION_NAME,
    PUBLIC_INGRESS_INTEGRATION_NAME,
    WORKLOAD_CONTAINER,
)
from integrations import PublicIngressData


@pytest.fixture
def mocked_container() -> MagicMock:
    return create_autospec(Container)


@pytest.fixture
def mocked_unit(mocked_container: MagicMock) -> MagicMock:
    mocked = create_autospec(Unit)
    mocked.get_container.return_value = mocked_container
    return mocked


@pytest.fixture
def mocked_event() -> MagicMock:
    return create_autospec(EventBase)


@pytest.fixture
def harness() -> Generator[Harness, None, None]:
    harness = Harness(HydraCharm)
    harness.set_model_name("testing")
    harness.set_can_connect(WORKLOAD_CONTAINER, True)
    harness.begin()
    harness.add_network("10.0.0.10")
    yield harness
    harness.cleanup()


@pytest.fixture
def mocked_workload_service(mocker: MockerFixture, harness: Harness) -> MagicMock:
    mocked = mocker.patch("charm.WorkloadService", autospec=True)
    harness.charm._workload_service = mocked
    return mocked


@pytest.fixture
def mocked_workload_service_version(mocker: MockerFixture) -> MagicMock:
    return mocker.patch(
        "charm.WorkloadService.version", new_callable=PropertyMock, return_value="1.0.0"
    )


@pytest.fixture
def mocked_pebble_service(mocker: MockerFixture, harness: Harness) -> MagicMock:
    mocked = mocker.patch("charm.PebbleService", autospec=True)
    harness.charm._pebble_service = mocked
    return mocked


@pytest.fixture
def mocked_charm_holistic_handler(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.HydraCharm._holistic_handler")


@pytest.fixture
def mocked_oauth_integration_created_handler(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.HydraCharm._on_oauth_integration_created")


@pytest.fixture
def peer_integration(harness: Harness) -> int:
    return harness.add_relation(PEER_INTEGRATION_NAME, "hydra")


@pytest.fixture
def database_integration(harness: Harness) -> int:
    return harness.add_relation(DATABASE_INTEGRATION_NAME, "postgresql-k8s")


@pytest.fixture
def public_ingress_integration(harness: Harness) -> int:
    return harness.add_relation(PUBLIC_INGRESS_INTEGRATION_NAME, "public-ingress")


@pytest.fixture
def oauth_integration(harness: Harness) -> int:
    return harness.add_relation(OAUTH_INTEGRATION_NAME, "requirer")


@pytest.fixture
def database_integration_data(harness: Harness, database_integration: int) -> None:
    harness.update_relation_data(
        database_integration,
        "postgresql-k8s",
        {
            "data": '{"database": "hydra", "extra-user-roles": "SUPERUSER"}',
            "database": "database",
            "endpoints": "endpoints",
            "username": "username",
            "password": "password",
        },
    )


@pytest.fixture
def public_ingress_integration_data(harness: Harness, public_ingress_integration: int) -> None:
    harness.update_relation_data(
        public_ingress_integration,
        "public-ingress",
        {
            "ingress": '{"url": "https://hydra.ory.com"}',
        },
    )


@pytest.fixture
def mocked_public_ingress_data(mocker: MockerFixture) -> PublicIngressData:
    mocked = mocker.patch(
        "charm.PublicIngressData.load",
        return_value=PublicIngressData(url=URL("https://hydra.ory.com")),
    )
    return mocked.return_value


@pytest.fixture
def mocked_oauth_client_config() -> dict:
    return {
        "redirect_uri": "https://example.oidc.client/callback",
        "scope": "openid email offline_access",
        "grant_types": [
            "authorization_code",
            "refresh_token",
            "client_credentials",
            "urn:ietf:params:oauth:grant-type:device_code",
        ],
        "audience": [],
        "token_endpoint_auth_method": "client_secret_basic",
    }
