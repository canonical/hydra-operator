# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import functools
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Awaitable, Callable, Optional

import httpx
import pytest
import pytest_asyncio
import yaml
from httpx import AsyncClient, HTTPStatusError, RequestError, Response
from juju.application import Application
from juju.unit import Unit
from jwt import PyJWKClient, PyJWKClientConnectionError
from pytest_operator.plugin import OpsTest

from constants import (
    ADMIN_INGRESS_INTEGRATION_NAME,
    LOGIN_UI_INTEGRATION_NAME,
    PUBLIC_INGRESS_INTEGRATION_NAME,
)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
HYDRA_APP = METADATA["name"]
HYDRA_IMAGE = METADATA["resources"]["oci-image"]["upstream-source"]
DB_APP = "postgresql-k8s"
CA_APP = "self-signed-certificates"
LOGIN_UI_APP = "identity-platform-login-ui-operator"
PUBLIC_INGRESS_APP = "public-ingress"
ADMIN_INGRESS_APP = "admin-ingress"
TRAEFIK_CHARM = "traefik-k8s"
ISTIO_INGRESS_CHARM = "istio-ingress-k8s"
ISTIO_CONTROL_PLANE_CHARM = "istio-k8s"
CLIENT_SECRET = "secret"
CLIENT_REDIRECT_URIS = ["https://example.com"]
PUBLIC_INGRESS_DOMAIN = "public"
ADMIN_INGRESS_DOMAIN = "admin"
PUBLIC_LOAD_BALANCER = f"{PUBLIC_INGRESS_APP}-istio"
ADMIN_LOAD_BALANCER = f"{ADMIN_INGRESS_APP}-lb"


async def integrate_dependencies(ops_test: OpsTest) -> None:
    await ops_test.model.integrate(HYDRA_APP, DB_APP)
    await ops_test.model.integrate(
        f"{HYDRA_APP}:{LOGIN_UI_INTEGRATION_NAME}", f"{LOGIN_UI_APP}:{LOGIN_UI_INTEGRATION_NAME}"
    )
    await ops_test.model.integrate(
        f"{HYDRA_APP}:{ADMIN_INGRESS_INTEGRATION_NAME}", ADMIN_INGRESS_APP
    )
    await ops_test.model.integrate(
        f"{HYDRA_APP}:{PUBLIC_INGRESS_INTEGRATION_NAME}", PUBLIC_INGRESS_APP
    )


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
async def leader_peer_integration_data(app_integration_data: Callable) -> Optional[dict]:
    return await app_integration_data(HYDRA_APP, HYDRA_APP)


async def get_k8s_service_address(namespace: str, service_name: str) -> str:
    cmd = [
        "kubectl",
        "-n",
        namespace,
        "get",
        f"service/{service_name}",
        "-o=jsonpath={.status.loadBalancer.ingress[0].ip}",
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await process.communicate()

    return stdout.decode().strip() if not process.returncode else ""


@pytest_asyncio.fixture
async def public_ingress_address(ops_test: OpsTest) -> str:
    return await get_k8s_service_address(ops_test.model_name, PUBLIC_LOAD_BALANCER)


@pytest_asyncio.fixture
async def admin_ingress_address(ops_test: OpsTest) -> str:
    return await get_k8s_service_address(ops_test.model_name, ADMIN_LOAD_BALANCER)


@pytest_asyncio.fixture
async def http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(verify=False) as client:
        yield client


@pytest_asyncio.fixture
async def get_hydra_jwks(
    ops_test: OpsTest,
    request: pytest.FixtureRequest,
    public_ingress_address: str,
    http_client: AsyncClient,
) -> Callable[[], Awaitable[Response]]:
    url = (
        f"https://{public_ingress_address}/{ops_test.model_name}-{HYDRA_APP}/.well-known/jwks.json"
    )

    async def wrapper() -> Response:
        return await http_client.get(
            url,
            headers={"Host": PUBLIC_INGRESS_DOMAIN},
            extensions={"sni_hostname": PUBLIC_INGRESS_DOMAIN},
        )

    return wrapper


@pytest_asyncio.fixture
async def get_openid_configuration(
    ops_test: OpsTest,
    public_ingress_address: str,
    http_client: AsyncClient,
) -> Response:
    url = f"https://{public_ingress_address}/{ops_test.model_name}-{HYDRA_APP}/.well-known/openid-configuration"
    return await http_client.get(
        url,
        headers={"Host": PUBLIC_INGRESS_DOMAIN},
        extensions={"sni_hostname": PUBLIC_INGRESS_DOMAIN},
    )


@pytest_asyncio.fixture
async def get_admin_clients(
    ops_test: OpsTest,
    admin_ingress_address: str,
    http_client: AsyncClient,
) -> Response:
    url = f"http://{admin_ingress_address}/{ops_test.model_name}-{HYDRA_APP}/admin/clients"
    return await http_client.get(url, headers={"Host": ADMIN_INGRESS_DOMAIN})


@pytest_asyncio.fixture
async def client_credential_request(
    ops_test: OpsTest,
    public_ingress_address: str,
    http_client: AsyncClient,
) -> Callable[[str, str], Awaitable[Response]]:
    async def wrapper(client_id: str, client_secret: str) -> Response:
        url = f"https://{public_ingress_address}/{ops_test.model_name}-{HYDRA_APP}/oauth2/token"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Host": PUBLIC_INGRESS_DOMAIN,
        }
        return await http_client.post(
            url,
            headers=headers,
            auth=(client_id, client_secret),
            data={
                "grant_type": "client_credentials",
                "scope": "openid profile",
            },
            extensions={"sni_hostname": PUBLIC_INGRESS_DOMAIN},
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


class CustomPyJWKClient(PyJWKClient):
    def __init__(self, uri: str, hostname: str) -> None:
        super().__init__(uri)
        self._hostname = hostname

    def fetch_data(self) -> dict:
        jwk_set = None
        try:
            with httpx.Client(verify=False) as client:
                response = client.get(
                    self.uri,
                    headers={"Host": self._hostname},
                    extensions={"sni_hostname": self._hostname},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                jwk_set = response.json()
        except (HTTPStatusError, RequestError, TimeoutError) as e:
            raise PyJWKClientConnectionError(f'Fail to fetch data from the url, err: "{e}"')
        else:
            return jwk_set
        finally:
            if self.jwk_set_cache is not None:
                self.jwk_set_cache.put(jwk_set)


@pytest_asyncio.fixture
async def jwks_client(ops_test: OpsTest, public_ingress_address: str) -> PyJWKClient:
    return CustomPyJWKClient(
        uri=f"https://{public_ingress_address}/{ops_test.model.name}-{HYDRA_APP}/.well-known/jwks.json",
        hostname=PUBLIC_INGRESS_DOMAIN,
    )


@pytest_asyncio.fixture(scope="module")
async def local_charm(ops_test: OpsTest) -> Path:
    return await ops_test.build_charm(".")


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
