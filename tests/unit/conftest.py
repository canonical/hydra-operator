# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Dict, Generator
from unittest.mock import MagicMock

import pytest
from ops.testing import Harness
from pytest_mock import MockerFixture

from charm import HydraCharm


@pytest.fixture()
def harness(mocked_kubernetes_service_patcher: Generator) -> Generator[Harness, None, None]:
    harness = Harness(HydraCharm)
    harness.set_model_name("testing")
    harness.set_leader(True)
    harness.begin()
    yield harness
    harness.cleanup()


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
def hydra_cli_client_json() -> Dict:
    return {
        "client_id": "07b318cf-9a9f-47b2-a288-972e671936a1",
        "client_name": "",
        "client_secret": "_hXRi23BeBc1kGhCQKRASz7nC6",
        "client_secret_expires_at": 0,
        "client_uri": "",
        "created_at": "2023-03-17T13:03:53Z",
        "grant_types": ["authorization_code"],
        "jwks": {},
        "logo_uri": "",
        "metadata": {},
        "owner": "",
        "policy_uri": "",
        "redirect_uris": ["https://example/oauth/callback"],
        "registration_access_token": "ory_at_1hxSDuA1Ivyvi6Sy0iHfUFOVcASiOp4ZzVY4frtKMKo.7FliqVHMff94gacuKLKCnWEiCqMxJYs8jHmSw8iP03k",
        "registration_client_uri": "http://localhost:4444/oauth2/register/07b318cf-9a9f-47b2-a288-972e671936a1",
        "request_object_signing_alg": "RS256",
        "response_types": ["code"],
        "scope": "offline_access offline openid",
        "subject_type": "public",
        "token_endpoint_auth_method": "client_secret_basic",
        "tos_uri": "",
        "updated_at": "2023-03-17T13:03:53.389214Z",
        "userinfo_signed_response_alg": "none",
    }


@pytest.fixture()
def mocked_create_client(mocker: MockerFixture, hydra_cli_client_json: Dict) -> Generator:
    mock = mocker.patch("charm.HydraCLI.create_client")
    mock.return_value = hydra_cli_client_json
    yield mock


@pytest.fixture()
def mocked_get_client(mocker: MockerFixture, hydra_cli_client_json: Dict) -> Generator:
    mock = mocker.patch("charm.HydraCLI.get_client")
    hydra_cli_client_json = dict(hydra_cli_client_json)
    hydra_cli_client_json.pop("client_secret", None)
    mock.return_value = hydra_cli_client_json
    yield mock


@pytest.fixture()
def mocked_update_client(mocker: MockerFixture, hydra_cli_client_json: Dict) -> Generator:
    mock = mocker.patch("charm.HydraCLI.update_client")
    hydra_cli_client_json = dict(hydra_cli_client_json)
    hydra_cli_client_json.pop("client_secret", None)
    hydra_cli_client_json.pop("registration_access_token", None)
    hydra_cli_client_json.pop("registration_client_uri", None)
    mock.return_value = hydra_cli_client_json
    yield mock


@pytest.fixture()
def mocked_list_client(mocker: MockerFixture, hydra_cli_client_json: Dict) -> Generator:
    mock = mocker.patch("charm.HydraCLI.list_clients")
    hydra_cli_client_json = dict(hydra_cli_client_json)
    hydra_cli_client_json.pop("client_secret", None)
    hydra_cli_client_json.pop("registration_access_token", None)
    hydra_cli_client_json.pop("registration_client_uri", None)
    ret = {"items": [dict(hydra_cli_client_json, client_id=f"client-{i}") for i in range(20)]}
    mock.return_value = ret
    yield mock


@pytest.fixture()
def mocked_delete_client(mocker: MockerFixture, hydra_cli_client_json: Dict) -> Generator:
    mock = mocker.patch("charm.HydraCLI.delete_client")
    mock.return_value = hydra_cli_client_json["client_id"]
    yield mock


@pytest.fixture()
def mocked_revoke_tokens(mocker: MockerFixture) -> Generator:
    mock = mocker.patch("charm.HydraCLI.delete_client_access_tokens")
    mock.return_value = "client_id"
    yield mock


@pytest.fixture()
def mocked_create_jwk(mocker: MockerFixture) -> Generator:
    mock = mocker.patch("charm.HydraCLI.create_jwk")
    mock.return_value = {
        "set": "hydra.openid.id-token",
        "keys": [
            {
                "alg": "RS256",
                "d": "a",
                "dp": "b",
                "dq": "c",
                "e": "AQAB",
                "kid": "183d04f5-9e7b-4d2e-91e6-5b91d17db16d",
                "kty": "RSA",
                "n": "d",
                "p": "e",
                "q": "f",
                "qi": "g",
                "use": "sig",
            }
        ],
    }
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


@pytest.fixture(autouse=True)
def mocked_log_proxy_consumer_setup_promtail(mocker: MockerFixture) -> MagicMock:
    mocked_setup_promtail = mocker.patch(
        "charms.loki_k8s.v0.loki_push_api.LogProxyConsumer._setup_promtail", return_value=None
    )
    return mocked_setup_promtail
