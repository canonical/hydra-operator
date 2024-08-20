# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import functools
import re
import ssl
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Awaitable, Callable, Optional

import httpx
import pytest
import pytest_asyncio
import yaml
from httpx import AsyncClient, Response
from juju.application import Application
from juju.unit import Unit
from jwt import PyJWKClient
from pytest_operator.plugin import OpsTest

from constants import (
    INTERNAL_INGRESS_INTEGRATION_NAME,
    LOGIN_UI_INTEGRATION_NAME,
    PUBLIC_INGRESS_INTEGRATION_NAME,
)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
HYDRA_APP = METADATA["name"]
HYDRA_IMAGE = METADATA["resources"]["oci-image"]["upstream-source"]
DB_APP = "postgresql-k8s"
CA_APP = "self-signed-certificates"
LOGIN_UI_APP = "identity-platform-login-ui-operator"
TRAEFIK_CHARM = "traefik-k8s"
TRAEFIK_ADMIN_APP = "traefik-admin"
TRAEFIK_PUBLIC_APP = "traefik-public"
CLIENT_SECRET = "secret"
CLIENT_REDIRECT_URIS = ["https://example.com"]
PUBLIC_INGRESS_DOMAIN = "public"
ADMIN_INGRESS_DOMAIN = "admin"


async def get_unit_data(ops_test: OpsTest, unit_name: str) -> dict:
    show_unit_cmd = (f"show-unit {unit_name}").split()
    _, stdout, _ = await ops_test.juju(*show_unit_cmd)
    cmd_output = yaml.safe_load(stdout)
    return cmd_output[unit_name]


async def get_integration_data(
    ops_test: OpsTest, app_name: str, integration_name: str, unit_num: int = 0
) -> Optional[dict]:
    data = await get_unit_data(ops_test, f"{app_name}/{unit_num}")
    return next(
        (
            integration
            for integration in data["relation-info"]
            if integration["endpoint"] == integration_name
        ),
        None,
    )


async def get_app_integration_data(
    ops_test: OpsTest,
    app_name: str,
    integration_name: str,
    unit_num: int = 0,
) -> Optional[dict]:
    data = await get_integration_data(ops_test, app_name, integration_name, unit_num)
    return data["application-data"] if data else None


@pytest_asyncio.fixture
async def app_integration_data(ops_test: OpsTest) -> Callable:
    return functools.partial(get_app_integration_data, ops_test)


@pytest_asyncio.fixture
async def login_ui_endpoint_integration_data(app_integration_data: Callable) -> Optional[dict]:
    return await app_integration_data(HYDRA_APP, LOGIN_UI_INTEGRATION_NAME)


@pytest_asyncio.fixture
async def leader_public_ingress_integration_data(app_integration_data: Callable) -> Optional[dict]:
    return await app_integration_data(HYDRA_APP, PUBLIC_INGRESS_INTEGRATION_NAME)


@pytest_asyncio.fixture
async def leader_internal_ingress_integration_data(
    app_integration_data: Callable,
) -> Optional[dict]:
    return await app_integration_data(HYDRA_APP, INTERNAL_INGRESS_INTEGRATION_NAME)


@pytest_asyncio.fixture
async def leader_peer_integration_data(app_integration_data: Callable) -> Optional[dict]:
    return await app_integration_data(HYDRA_APP, HYDRA_APP)


async def unit_address(ops_test: OpsTest, *, app_name: str, unit_num: int = 0) -> str:
    status = await ops_test.model.get_status()
    return status["applications"][app_name]["units"][f"{app_name}/{unit_num}"]["address"]


@pytest_asyncio.fixture
async def public_address() -> Callable[[OpsTest, int], Awaitable[str]]:
    return functools.partial(unit_address, app_name=TRAEFIK_PUBLIC_APP)


@pytest_asyncio.fixture
async def admin_address() -> Callable[[OpsTest, int], Awaitable[str]]:
    return functools.partial(unit_address, app_name=TRAEFIK_ADMIN_APP)


@pytest_asyncio.fixture
async def http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(verify=False) as client:
        yield client


@pytest_asyncio.fixture
async def get_hydra_jwks(
    ops_test: OpsTest,
    request: pytest.FixtureRequest,
    public_address: Callable,
    admin_address: Callable,
    http_client: AsyncClient,
) -> Callable[[], Awaitable[Response]]:
    address_func = admin_address if request.param == "admin" else public_address
    scheme = "http" if request.param == "admin" else "https"

    async def wrapper() -> Response:
        address = await address_func(ops_test)
        url = f"{scheme}://{address}/{ops_test.model_name}-{HYDRA_APP}/.well-known/jwks.json"
        return await http_client.get(url)

    return wrapper


@pytest_asyncio.fixture
async def get_openid_configuration(
    ops_test: OpsTest, public_address: Callable, http_client: AsyncClient
) -> Response:
    address = await public_address(ops_test)
    url = f"https://{address}/{ops_test.model_name}-{HYDRA_APP}/.well-known/openid-configuration"
    return await http_client.get(url)


@pytest_asyncio.fixture
async def get_admin_clients(
    ops_test: OpsTest, admin_address: Callable, http_client: AsyncClient
) -> Response:
    address = await admin_address(ops_test)
    url = f"http://{address}/{ops_test.model_name}-{HYDRA_APP}/admin/clients"
    return await http_client.get(url)


@pytest_asyncio.fixture
async def client_credential_request(
    ops_test: OpsTest, public_address: Callable, http_client: AsyncClient
) -> Callable[[str, str], Awaitable[Response]]:
    async def wrapper(client_id: str, client_secret: str) -> Response:
        address = await public_address(ops_test)
        url = f"https://{address}/{ops_test.model_name}-{HYDRA_APP}/oauth2/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        return await http_client.post(
            url,
            headers=headers,
            auth=(client_id, client_secret),
            data={
                "grant_type": "client_credentials",
                "scope": "openid profile",
            },
        )

    return wrapper


@pytest.fixture(scope="session")
def hydra_version() -> str:
    matched = re.search(r"(?P<version>\d+\.\d+\.\d+)", HYDRA_IMAGE)
    return f"v{matched.group('version')}" if matched else ""


@pytest.fixture
def migration_key(ops_test: OpsTest) -> str:
    db_integration = next(
        (
            integration
            for integration in ops_test.model.relations
            if integration.matches(f"{HYDRA_APP}:pg-database", f"{DB_APP}:database")
        ),
        None,
    )
    return f"migration_version_{db_integration.entity_id}" if db_integration else ""


@pytest.fixture
def hydra_application(ops_test: OpsTest) -> Application:
    return ops_test.model.applications[HYDRA_APP]


@pytest.fixture
def hydra_unit(hydra_application: Application) -> Unit:
    return hydra_application.units[0]


@pytest_asyncio.fixture
async def oauth_clients(hydra_unit: Unit) -> dict[str, str]:
    action = await hydra_unit.run_action("list-oauth-clients")
    return (await action.wait()).results


@pytest_asyncio.fixture
async def jwks_client(ops_test: OpsTest, public_address: Callable) -> PyJWKClient:
    address = await public_address(ops_test)

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    return PyJWKClient(
        f"https://{address}/{ops_test.model.name}-{HYDRA_APP}/.well-known/jwks.json",
        ssl_context=ssl_ctx,
    )


@asynccontextmanager
async def remove_integration(
    ops_test: OpsTest, remote_app_name: str, integration_name: str
) -> AsyncGenerator[None, None]:
    remove_integration_cmd = (
        f"remove-relation {HYDRA_APP}:{integration_name} {remote_app_name}"
    ).split()
    await ops_test.juju(*remove_integration_cmd)
    await ops_test.model.wait_for_idle(
        apps=[remote_app_name],
        status="active",
    )

    try:
        yield
    finally:
        await ops_test.model.integrate(f"{HYDRA_APP}:{integration_name}", remote_app_name)
        await ops_test.model.wait_for_idle(
            apps=[HYDRA_APP, remote_app_name],
            status="active",
        )
