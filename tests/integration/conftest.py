# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import os
import re
import secrets
import ssl
import subprocess
from contextlib import suppress
from pathlib import Path
from typing import Callable, Generator

import jubilant
import pytest
import requests
from integration.constants import (
    DB_APP,
    HYDRA_APP,
    HYDRA_IMAGE,
    LOGIN_UI_APP,
    TRAEFIK_ADMIN_APP,
    TRAEFIK_PUBLIC_APP,
)
from integration.utils import (
    get_app_integration_data,
    get_integration_data,
    get_unit_address,
    juju_model_factory,
)
from jwt import PyJWKClient

from src.constants import (
    INTERNAL_ROUTE_INTEGRATION_NAME,
    LOGIN_UI_INTEGRATION_NAME,
    PUBLIC_ROUTE_INTEGRATION_NAME,
)


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add custom command-line options for model management and deployment control.

    This function adds the following options:
    --keep-models, --no-teardown: Keep the Juju model after the test is finished.
    --model: Specify the Juju model to run the tests on.
    --no-deploy, --no-setup: Skip deployment of the charm.
    """
    parser.addoption(
        "--keep-models",
        "--no-teardown",
        action="store_true",
        dest="no_teardown",
        default=False,
        help="Keep the model after the test is finished.",
    )
    parser.addoption(
        "--model",
        action="store",
        dest="model",
        default=None,
        help="The model to run the tests on.",
    )
    parser.addoption(
        "--no-deploy",
        "--no-setup",
        action="store_true",
        dest="no_setup",
        default=False,
        help="Skip deployment of the charm.",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers for test selection based on deployment and model management.

    This function registers the following markers:
    setup: Skip tests if the charm is already deployed.
    teardown: Skip tests if the no_teardown option is set.
    """
    config.addinivalue_line("markers", "setup: tests that setup some parts of the environment")
    config.addinivalue_line("markers", "upgrade: tests that upgrade the charm")
    config.addinivalue_line(
        "markers", "teardown: tests that teardown some parts of the environment."
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Modify collected test items based on command-line options.

    This function skips tests with specific markers based on the provided command-line options:
    - If no_setup is set, tests marked with "setup" are skipped.
    - If no_teardown is set, tests marked with "teardown" are skipped.
    """
    skip_setup = pytest.mark.skip(reason="no_setup provided")
    skip_teardown = pytest.mark.skip(reason="no_teardown provided")
    for item in items:
        if config.getoption("no_setup") and "setup" in item.keywords:
            item.add_marker(skip_setup)
        if config.getoption("no_teardown") and "teardown" in item.keywords:
            item.add_marker(skip_teardown)


@pytest.fixture(scope="module")
def juju(request: pytest.FixtureRequest) -> Generator[jubilant.Juju, None, None]:
    """Create a temporary Juju model for integration tests."""
    model_name = request.config.getoption("--model")
    if not model_name:
        model_name = f"test-hydra-{secrets.token_hex(4)}"

    juju_ = juju_model_factory(model_name)
    juju_.wait_timeout = 10 * 60

    try:
        yield juju_
    finally:
        if request.session.testsfailed:
            log = juju_.debug_log(limit=1000)
            print(log, end="")

        no_teardown = bool(request.config.getoption("--no-teardown"))
        keep_model = no_teardown or request.session.testsfailed > 0
        if not keep_model:
            with suppress(jubilant.CLIError):
                args = [
                    "destroy-model",
                    juju_.model,
                    "--no-prompt",
                    "--destroy-storage",
                    "--force",
                    "--timeout",
                    "600s",
                ]
                juju_.cli(*args, include_model=False)


@pytest.fixture(scope="session")
def local_charm() -> Path:
    """Get the path to the charm-under-test."""
    # in GitHub CI, charms are built with charmcraftcache and uploaded to
    charm: str | Path | None = os.getenv("CHARM_PATH")
    if not charm:
        subprocess.run(["charmcraft", "pack"], check=True)
        if not (charms := list(Path(".").glob("*.charm"))):
            raise RuntimeError("Charm not found and build failed")
        charm = charms[0].absolute()
    return Path(charm)


@pytest.fixture
def http_client() -> Generator[requests.Session, None, None]:
    with requests.Session() as client:
        client.verify = False
        yield client


def integrate_dependencies(juju: jubilant.Juju) -> None:
    juju.integrate(HYDRA_APP, DB_APP)
    juju.integrate(f"{HYDRA_APP}:{PUBLIC_ROUTE_INTEGRATION_NAME}", TRAEFIK_PUBLIC_APP)
    juju.integrate(f"{HYDRA_APP}:{INTERNAL_ROUTE_INTEGRATION_NAME}", TRAEFIK_ADMIN_APP)
    juju.integrate(
        f"{HYDRA_APP}:{LOGIN_UI_INTEGRATION_NAME}", f"{LOGIN_UI_APP}:{LOGIN_UI_INTEGRATION_NAME}"
    )


@pytest.fixture
def app_integration_data(juju: jubilant.Juju) -> Callable:
    def _get_data(app_name: str, integration_name: str, unit_num: int = 0):
        return get_app_integration_data(juju, app_name, integration_name, unit_num)

    return _get_data


@pytest.fixture
def login_ui_endpoint_integration_data(app_integration_data: Callable) -> dict | None:
    return app_integration_data(HYDRA_APP, LOGIN_UI_INTEGRATION_NAME)


@pytest.fixture
def leader_public_route_integration_data(app_integration_data: Callable) -> dict | None:
    return app_integration_data(HYDRA_APP, PUBLIC_ROUTE_INTEGRATION_NAME)


@pytest.fixture
def leader_internal_ingress_integration_data(
    app_integration_data: Callable,
) -> dict | None:
    return app_integration_data(HYDRA_APP, INTERNAL_ROUTE_INTEGRATION_NAME)


@pytest.fixture
def leader_peer_integration_data(app_integration_data: Callable) -> dict | None:
    return app_integration_data(HYDRA_APP, HYDRA_APP)


@pytest.fixture
def public_address(juju: jubilant.Juju) -> str:
    return get_unit_address(juju, app_name=TRAEFIK_PUBLIC_APP)


@pytest.fixture
def admin_address(juju: jubilant.Juju) -> str:
    return get_unit_address(juju, app_name=TRAEFIK_ADMIN_APP)


@pytest.fixture
def get_hydra_jwks(
    juju: jubilant.Juju,
    request: pytest.FixtureRequest,
    http_client: requests.Session,
) -> Callable[[], requests.Response]:
    # Use closures to access fixtures and params
    def wrapper() -> requests.Response:
        target = request.param
        if target == "admin":
            address = get_unit_address(juju, app_name=TRAEFIK_ADMIN_APP)
            scheme = "http"
        else:
            address = get_unit_address(juju, app_name=TRAEFIK_PUBLIC_APP)
            scheme = "https"

        url = f"{scheme}://{address}/.well-known/jwks.json"
        return http_client.get(url)

    return wrapper


@pytest.fixture
def get_openid_configuration(
    public_address: str, http_client: requests.Session
) -> requests.Response:
    url = f"https://{public_address}/.well-known/openid-configuration"
    return http_client.get(url)


@pytest.fixture
def get_admin_clients(admin_address: str, http_client: requests.Session) -> requests.Response:
    url = f"http://{admin_address}/admin/clients"
    return http_client.get(url)


@pytest.fixture
def client_credential_request(
    public_address: str, http_client: requests.Session
) -> Callable[[str, str], requests.Response]:
    def wrapper(client_id: str, client_secret: str) -> requests.Response:
        url = f"https://{public_address}/oauth2/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        return http_client.post(
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
def migration_key(juju: jubilant.Juju) -> str:
    data = get_integration_data(juju, HYDRA_APP, "pg-database")
    return f"migration_version_{data['relation-id']}" if data else ""


@pytest.fixture
def oauth_clients(juju: jubilant.Juju) -> list[dict[str, str]]:
    action = juju.run(f"{HYDRA_APP}/0", "list-oauth-clients")
    clients_json = action.results["clients"]
    return json.loads(clients_json)


@pytest.fixture
def jwks_client(public_address: str) -> PyJWKClient:
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    return PyJWKClient(
        f"https://{public_address}/.well-known/jwks.json",
        ssl_context=ssl_ctx,
    )
