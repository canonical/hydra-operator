# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Dict, Generator
from unittest.mock import MagicMock

import pytest
from ops.testing import Harness
from pytest_mock import MockerFixture

from charm import HydraCharm


@pytest.fixture()
def harness(mocked_kubernetes_service_patcher: MagicMock) -> Harness:
    harness = Harness(HydraCharm)
    harness.set_model_name("testing")
    harness.set_leader(True)
    harness.begin()
    return harness


@pytest.fixture()
def mocked_kubernetes_service_patcher(mocker: MockerFixture) -> Generator:
    mocked_service_patcher = mocker.patch("charm.KubernetesServicePatch")
    mocked_service_patcher.return_value = lambda x, y: None
    yield mocked_service_patcher


@pytest.fixture()
def mocked_hydra_is_running(mocker: MockerFixture) -> Generator:
    yield mocker.patch("charm.HydraCharm._hydra_service_is_running", return_value=True)


@pytest.fixture()
def mocked_sql_migration(mocker: MockerFixture) -> Generator:
    mocked_sql_migration = mocker.patch("charm.HydraCharm._run_sql_migration")
    yield mocked_sql_migration


@pytest.fixture()
def mocked_create_client(mocker: MockerFixture) -> Generator:
    mock = mocker.patch("charm.HydraCLI.create_client")
    mock.return_value = {"client_id": "client_id", "client_secret": "client_secret"}
    yield mock


@pytest.fixture()
def mocked_update_client(mocker: MockerFixture) -> Generator:
    mock = mocker.patch("charm.HydraCLI.update_client")
    mock.return_value = {"client_id": "client_id", "client_secret": "client_secret"}
    yield mock


@pytest.fixture()
def mocked_delete_client(mocker: MockerFixture) -> Generator:
    mock = mocker.patch("charm.HydraCLI.delete_client")
    mock.return_value = "client_id"
    yield mock


@pytest.fixture()
def mocked_set_provider_info(mocker: MockerFixture) -> Generator:
    yield mocker.patch("charm.OAuthProvider.set_provider_info_in_relation_data")


@pytest.fixture()
def mocked_set_client_credentials(mocker: MockerFixture) -> Generator:
    yield mocker.patch("charm.OAuthProvider.set_client_credentials_in_relation_data")


@pytest.fixture()
def mocked_fqdn(mocker: MockerFixture) -> Generator:
    mocked_fqdn = mocker.patch("socket.getfqdn")
    mocked_fqdn.return_value = "hydra"
    return mocked_fqdn


@pytest.fixture()
def client_config() -> Dict:
    return {
        "redirect_uri": "https://example.oidc.client/callback",
        "scope": "openid email offline_access",
        "grant_types": ["authorization_code", "refresh_token"],
        "audience": [],
        "token_endpoint_auth_method": "client_secret_basic",
    }
