# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from dataclasses import replace
from json import dumps
from unittest.mock import MagicMock, create_autospec

import pytest
from ops.pebble import CheckLevel, CheckStartup, CheckStatus, Layer, ServiceStatus
from ops.testing import (
    CheckInfo,
    Container,
    Context,
    Exec,
    PeerRelation,
    Relation,
    Secret,
    State,
)
from pytest_mock import MockerFixture
from yarl import URL

from charm import HydraCharm
from constants import (
    COOKIE_SECRET_KEY,
    COOKIE_SECRET_LABEL,
    DATABASE_INTEGRATION_NAME,
    HYDRA_TOKEN_HOOK_INTEGRATION_NAME,
    INTERNAL_ROUTE_INTEGRATION_NAME,
    LOGIN_UI_INTEGRATION_NAME,
    OAUTH_INTEGRATION_NAME,
    PEBBLE_READY_CHECK_NAME,
    PEER_INTEGRATION_NAME,
    PUBLIC_ROUTE_INTEGRATION_NAME,
    SYSTEM_SECRET_KEY,
    SYSTEM_SECRET_LABEL,
    WORKLOAD_CONTAINER,
    WORKLOAD_SERVICE,
)
from integrations import InternalIngressData, PublicRouteData
from services import PEBBLE_LAYER_DICT

OAUTH_CLIENT_DATA = {
    "client_id": "2d3a69ba-1ee9-4784-9dc0-f92695d6d967",
    "client_name": "aba",
    "client_secret": "XF9j2BPvrwNFnIZj5tLeGNWB51",
    "client_secret_expires_at": 0,
    "client_uri": "",
    "created_at": "2026-01-23T09:25:10Z",
    "grant_types": [
        "authorization_code",
        "refresh_token",
        "urn:ietf:params:oauth:grant-type:device_code",
    ],
    "jwks": {},
    "logo_uri": "",
    "metadata": {},
    "owner": "",
    "policy_uri": "",
    "redirect_uris": ["http://example.com/callback"],
    "registration_access_token": "ory_at_GKK3WhbEXgjjd9YqtT4K5EySLNmJFq0z5vg5mfXRzWU.N9C8EM_Tyrcp3HozhQQsIAjMlZ8XM1ZuAVpSysxs-0c",
    "registration_client_uri": "http://localhost:4444/oauth2/register",
    "request_object_signing_alg": "RS256",
    "response_types": ["code"],
    "scope": "openid offline_access phone email profile",
    "subject_type": "public",
    "token_endpoint_auth_method": "client_secret_basic",
    "tos_uri": "",
    "updated_at": "2026-01-23T09:25:10.046978Z",
    "userinfo_signed_response_alg": "none",
}


@pytest.fixture()
def mocked_resource_patch(mocker: MockerFixture) -> MagicMock:
    mocked = mocker.patch(
        "charms.observability_libs.v0.kubernetes_compute_resources_patch.ResourcePatcher",
        autospec=True,
    )
    mocked.return_value.is_failed.return_value = (False, "")
    mocked.return_value.is_in_progress.return_value = False
    return mocked


@pytest.fixture(autouse=True)
def mocked_k8s_resource_patch(mocker: MockerFixture, mocked_resource_patch: MagicMock) -> None:
    mocker.patch.multiple(
        "charm.KubernetesComputeResourcesPatch",
        _namespace="testing",
        _patch=lambda *a, **kw: True,
        is_ready=lambda *a, **kw: True,
    )


@pytest.fixture
def mocked_container() -> MagicMock:
    return create_autospec(Container)


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


@pytest.fixture
def mocked_oauth_client() -> dict:
    return OAUTH_CLIENT_DATA


@pytest.fixture
def mocked_public_route_data(mocker: MockerFixture) -> PublicRouteData:
    mocked = mocker.patch(
        "charm.PublicRouteData.load",
        return_value=PublicRouteData(url=URL("https://hydra.ory.com")),
    )
    return mocked.return_value


@pytest.fixture
def mocked_internal_ingress_data(mocker: MockerFixture) -> InternalIngressData:
    mocked = mocker.patch(
        "charm.InternalIngressData.load",
        return_value=InternalIngressData(
            public_endpoint=URL("http://public.hydra.com"),
            admin_endpoint=URL("http://admin.hydra.com"),
        ),
    )
    return mocked.return_value


@pytest.fixture
def mocked_holistic_handler(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.HydraCharm._holistic_handler")


@pytest.fixture
def context():
    return Context(HydraCharm)


@pytest.fixture
def hydra_workload_version() -> str:
    return "v1.0.0"


@pytest.fixture
def hydra_version_exec(hydra_workload_version: str) -> Exec:
    return Exec(
        ["hydra", "version"],
        return_code=0,
        stdout=(
            f"Version:    {hydra_workload_version}\n"
            "Git Hash:   43214dsfasdf431\n"
            "Build Time: 2024-01-01T00:00:00Z"
        ),
    )


@pytest.fixture
def hydra_migrate_exec() -> Exec:
    return Exec(
        ["hydra", "migrate", "sql", "-e", "--yes"],
        return_code=0,
    )


@pytest.fixture
def hydra_create_jwk_exec() -> Exec:
    return Exec(
        ["hydra", "create", "jwk"],
        return_code=0,
    )


@pytest.fixture
def hydra_list_clients_exec(mocked_oauth_client: dict) -> Exec:
    return Exec(
        ["hydra", "list", "clients"],
        return_code=0,
        stdout=dumps([{k: v for k, v in mocked_oauth_client.items() if k != "client_secret"}]),
    )


@pytest.fixture
def hydra_get_client_exec(mocked_oauth_client: dict) -> Exec:
    return Exec(
        ["hydra", "get", "client"],
        return_code=0,
        stdout=dumps({k: v for k, v in mocked_oauth_client.items() if k != "client_secret"}),
    )


@pytest.fixture
def hydra_create_client_exec(mocked_oauth_client: dict) -> Exec:
    return Exec(
        ["hydra", "create", "client"],
        return_code=0,
        stdout=dumps(mocked_oauth_client),
    )


@pytest.fixture
def hydra_update_client_exec(mocked_oauth_client: dict) -> Exec:
    return Exec(
        ["hydra", "update", "client"],
        return_code=0,
        stdout=dumps({k: v for k, v in mocked_oauth_client.items() if k != "client_secret"}),
    )


@pytest.fixture
def hydra_delete_client_exec(mocked_oauth_client: dict) -> Exec:
    return Exec(
        ["hydra", "delete", "client"],
        return_code=0,
        stdout=dumps(mocked_oauth_client["client_id"]),
    )


@pytest.fixture
def hydra_delete_access_token_exec() -> Exec:
    return Exec(
        ["hydra", "delete", "access-tokens"],
        return_code=0,
    )


@pytest.fixture
def container(
    hydra_version_exec: Exec,
    hydra_migrate_exec: Exec,
    hydra_create_jwk_exec: Exec,
    hydra_list_clients_exec: Exec,
    hydra_get_client_exec: Exec,
    hydra_create_client_exec: Exec,
    hydra_update_client_exec: Exec,
    hydra_delete_client_exec: Exec,
    hydra_delete_access_token_exec: Exec,
) -> Container:
    return Container(
        name=WORKLOAD_CONTAINER,
        can_connect=True,
        execs={
            hydra_version_exec,
            hydra_migrate_exec,
            hydra_create_jwk_exec,
            hydra_list_clients_exec,
            hydra_get_client_exec,
            hydra_create_client_exec,
            hydra_update_client_exec,
            hydra_delete_client_exec,
            hydra_delete_access_token_exec,
        },
        service_statuses={WORKLOAD_SERVICE: ServiceStatus.ACTIVE},
        layers={
            "hydra": Layer(PEBBLE_LAYER_DICT),
        },
        check_infos=[
            CheckInfo(
                name=PEBBLE_READY_CHECK_NAME,
                level=CheckLevel.READY,
                status=CheckStatus.UP,
                startup=CheckStartup.UNSET,
                threshold=3,
            )
        ],
    )


@pytest.fixture
def peer_relation() -> PeerRelation:
    return PeerRelation(PEER_INTEGRATION_NAME)


@pytest.fixture
def peer_relation_ready(db_relation: Relation, hydra_workload_version: str) -> PeerRelation:
    return PeerRelation(
        PEER_INTEGRATION_NAME,
        local_app_data={f"migration_version_{db_relation.id}": dumps(hydra_workload_version)},
    )


@pytest.fixture
def db_relation() -> Relation:
    return Relation(DATABASE_INTEGRATION_NAME)


@pytest.fixture
def db_relation_ready(db_relation: Relation) -> Relation:
    return replace(
        db_relation,
        remote_app_data={
            "database": "database",
            "endpoints": "endpoints",
            "username": "username",
            "password": "password",
        },
    )


@pytest.fixture
def public_route_relation() -> Relation:
    return Relation(PUBLIC_ROUTE_INTEGRATION_NAME)


@pytest.fixture
def public_route_relation_ready() -> Relation:
    return Relation(
        PUBLIC_ROUTE_INTEGRATION_NAME,
        remote_app_data={"external_host": "example.com", "scheme": "https"},
    )


@pytest.fixture
def internal_route_relation() -> Relation:
    return Relation(INTERNAL_ROUTE_INTEGRATION_NAME)


@pytest.fixture
def internal_route_relation_ready() -> Relation:
    return Relation(
        INTERNAL_ROUTE_INTEGRATION_NAME,
        remote_app_data={"external_host": "internal.com", "scheme": "https"},
    )


@pytest.fixture
def login_ui_relation() -> Relation:
    return Relation(LOGIN_UI_INTEGRATION_NAME)


@pytest.fixture
def login_ui_relation_ready(login_ui_relation: Relation) -> Relation:
    return replace(
        login_ui_relation,
        remote_app_data={
            "consent_url": "https://login-ui.example.com/consent",
            "error_url": "https://login-ui.example.com/error",
            "login_url": "https://login-ui.example.com/login",
            "oidc_error_url": "https://login-ui.example.com/oidc_error",
            "device_verification_url": "https://login-ui.example.com/device_verification",
            "post_device_done_url": "https://login-ui.example.com/post_device_done",
            "recovery_url": "https://login-ui.example.com/recovery",
            "registration_url": "https://login-ui.example.com/registration",
            "settings_url": "https://login-ui.example.com/settings",
            "webauthn_settings_url": "https://login-ui.example.com/webauthn_settings",
        },
    )


@pytest.fixture
def token_hook_relation() -> Relation:
    return Relation(HYDRA_TOKEN_HOOK_INTEGRATION_NAME)


@pytest.fixture
def oauth_relation() -> Relation:
    return Relation(OAUTH_INTEGRATION_NAME)


@pytest.fixture
def hydra_endpoint_relation() -> Relation:
    return Relation("hydra-endpoint-info")


@pytest.fixture
def hydra_secrets() -> list[Secret]:
    return [
        Secret(
            owner="app",
            label=COOKIE_SECRET_LABEL,
            tracked_content={COOKIE_SECRET_KEY: "cookie"},
        ),
        Secret(
            owner="app",
            label=SYSTEM_SECRET_LABEL,
            tracked_content={SYSTEM_SECRET_KEY: "system"},
        ),
    ]


def create_state(
    leader: bool = True,
    secrets: list | None = None,
    relations: list | None = None,
    containers: list | None = None,
    config: dict | None = None,
    workload_version: str = "v1.0.0",
    hydra_is_running: bool = True,
    can_connect: bool = True,
) -> State:
    if secrets is None:
        secrets = []
    if relations is None:
        relations = []
    if containers is None:
        container_args = {
            "name": WORKLOAD_CONTAINER,
            "can_connect": can_connect,
            "execs": {
                Exec(
                    ["hydra", "version"],
                    return_code=0,
                    stdout=(
                        f"Version:    {workload_version}\n"
                        "Git Hash:   43214dsfasdf431\n"
                        "Build Time: 2024-01-01T00:00:00Z"
                    ),
                ),
                Exec(
                    ["hydra", "migrate", "sql", "-e", "--yes"],
                    return_code=0,
                ),
                Exec(
                    ["hydra", "create", "jwk"],
                    return_code=0,
                ),
                Exec(
                    ["hydra", "list", "clients"],
                    return_code=0,
                    stdout=dumps([
                        {k: v for k, v in OAUTH_CLIENT_DATA.items() if k != "client_secret"}
                    ]),
                ),
                Exec(
                    ["hydra", "get", "client"],
                    return_code=0,
                    stdout=dumps({
                        k: v for k, v in OAUTH_CLIENT_DATA.items() if k != "client_secret"
                    }),
                ),
                Exec(
                    ["hydra", "create", "client"],
                    return_code=0,
                    stdout=dumps(OAUTH_CLIENT_DATA["client_id"]),
                ),
                Exec(
                    ["hydra", "update", "client"],
                    return_code=0,
                    stdout=dumps({
                        k: v for k, v in OAUTH_CLIENT_DATA.items() if k != "client_secret"
                    }),
                ),
                Exec(
                    ["hydra", "delete", "client"],
                    return_code=0,
                    stdout=dumps(OAUTH_CLIENT_DATA["client_id"]),
                ),
                Exec(
                    ["hydra", "delete", "access-tokens"],
                    return_code=0,
                ),
            },
        }
        if hydra_is_running:
            container_args["service_statuses"] = {WORKLOAD_SERVICE: ServiceStatus.ACTIVE}
            container_args["layers"] = {
                "hydra": Layer(PEBBLE_LAYER_DICT),
            }
            container_args["check_infos"] = [
                CheckInfo(
                    name=PEBBLE_READY_CHECK_NAME,
                    level=CheckLevel.READY,
                    status=CheckStatus.UP,
                    startup=CheckStartup.UNSET,
                    threshold=3,
                )
            ]
        containers = [Container(**container_args)]
    if config is None:
        config = {}

    return State(
        leader=leader,
        secrets=secrets,
        containers=containers,
        relations=relations,
        config=config,
        workload_version=workload_version,
    )
