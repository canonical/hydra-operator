#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import http
import json
import logging
from pathlib import Path
from typing import Awaitable, Callable, Optional

import jwt
import pytest
from conftest import (
    ADMIN_INGRESS_DOMAIN,
    CA_APP,
    CLIENT_REDIRECT_URIS,
    CLIENT_SECRET,
    DB_APP,
    HYDRA_APP,
    HYDRA_IMAGE,
    LOGIN_UI_APP,
    PUBLIC_INGRESS_DOMAIN,
    TRAEFIK_ADMIN_APP,
    TRAEFIK_CHARM,
    TRAEFIK_PUBLIC_APP,
    integrate_dependencies,
    remove_integration,
)
from httpx import Response
from juju.application import Application
from juju.unit import Unit
from pytest_operator.plugin import OpsTest
from yarl import URL

from constants import (
    DATABASE_INTEGRATION_NAME,
    LOGIN_UI_INTEGRATION_NAME,
    PUBLIC_ROUTE_INTEGRATION_NAME,
)

logger = logging.getLogger(__name__)
system_secret = None
cookie_secret = None


@pytest.mark.skip_if_deployed
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, local_charm: Path) -> None:
    # Deploy dependencies
    await ops_test.model.deploy(
        entity_url=DB_APP,
        channel="14/stable",
        series="jammy",
        trust=True,
    )
    await ops_test.model.deploy(
        CA_APP,
        channel="latest/stable",
        trust=True,
    )
    await ops_test.model.deploy(
        TRAEFIK_CHARM,
        application_name=TRAEFIK_PUBLIC_APP,
        channel="latest/edge",  # using edge to take advantage of the raw args in traefik route
        config={"external_hostname": PUBLIC_INGRESS_DOMAIN},
        trust=True,
    )
    await ops_test.model.deploy(
        TRAEFIK_CHARM,
        application_name=TRAEFIK_ADMIN_APP,
        channel="latest/stable",
        config={"external_hostname": ADMIN_INGRESS_DOMAIN},
        trust=True,
    )
    await ops_test.model.deploy(
        LOGIN_UI_APP,
        channel="latest/edge",
        trust=True,
    )

    await ops_test.model.integrate(f"{TRAEFIK_PUBLIC_APP}:certificates", f"{CA_APP}:certificates")
    # await ops_test.model.integrate(TRAEFIK_PUBLIC_APP, f"{LOGIN_UI_APP}:public-route") # TODO @shipperizer change this once login-ui is g2g
    await ops_test.model.integrate(TRAEFIK_PUBLIC_APP, f"{LOGIN_UI_APP}:ingress")

    await ops_test.model.deploy(
        application_name=HYDRA_APP,
        entity_url=str(local_charm),
        resources={"oci-image": HYDRA_IMAGE},
        series="jammy",
        trust=True,
    )

    # Integrate with dependencies
    await integrate_dependencies(ops_test)

    await asyncio.gather(
        ops_test.model.wait_for_idle(
            apps=[HYDRA_APP],
            raise_on_blocked=False,
            status="active",
            timeout=5 * 60,
        ),
    )


async def test_peer_integration(
    leader_peer_integration_data: Optional[dict],
    hydra_version: str,
    migration_key: str,
) -> None:
    assert leader_peer_integration_data
    assert json.loads(leader_peer_integration_data[migration_key]) == hydra_version


async def test_login_ui_endpoint_integration(
    login_ui_endpoint_integration_data: Optional[dict],
) -> None:
    assert login_ui_endpoint_integration_data
    assert all(login_ui_endpoint_integration_data.values())


@pytest.mark.parametrize("get_hydra_jwks", ["public"], indirect=True)
async def test_public_route_integration(
    ops_test: OpsTest,
    leader_public_route_integration_data: Optional[dict],
    get_hydra_jwks: Callable[[], Awaitable[Response]],
) -> None:
    assert leader_public_route_integration_data
    assert leader_public_route_integration_data["external_host"] == PUBLIC_INGRESS_DOMAIN
    assert leader_public_route_integration_data["scheme"] == "https"

    resp = await get_hydra_jwks()
    assert resp.status_code == http.HTTPStatus.OK


async def test_openid_configuration_endpoint(
    ops_test: OpsTest, get_openid_configuration: Response
) -> None:
    base_path = URL(f"https://{PUBLIC_INGRESS_DOMAIN}")
    assert get_openid_configuration.status_code == http.HTTPStatus.OK

    payload = get_openid_configuration.json()
    assert payload["issuer"] == str(base_path)
    assert payload["authorization_endpoint"] == str(base_path / "oauth2/auth")
    assert payload["token_endpoint"] == str(base_path / "oauth2/token")
    assert payload["userinfo_endpoint"] == str(base_path / "userinfo")
    assert payload["jwks_uri"] == str(base_path / ".well-known/jwks.json")


@pytest.mark.parametrize("get_hydra_jwks", ["admin"], indirect=True)
async def test_internal_ingress_integration(
    leader_internal_ingress_integration_data: Optional[dict],
    get_admin_clients: Response,
    get_hydra_jwks: Callable[[], Awaitable[Response]],
) -> None:
    assert leader_internal_ingress_integration_data
    assert leader_internal_ingress_integration_data["external_host"] == ADMIN_INGRESS_DOMAIN
    assert leader_internal_ingress_integration_data["scheme"] == "http"

    # examine the admin endpoint
    assert get_admin_clients.status_code == http.HTTPStatus.OK

    # examine the public endpoint
    resp = await get_hydra_jwks()
    assert resp.status_code == http.HTTPStatus.OK


async def test_create_oauth_client_action(hydra_unit: Unit) -> None:
    action = await hydra_unit.run_action(
        "create-oauth-client",
        **{
            "redirect-uris": CLIENT_REDIRECT_URIS,
            "client-secret": CLIENT_SECRET,
            "grant-types": ["client_credentials"],
        },
    )
    res = (await action.wait()).results

    assert res["client-secret"] == CLIENT_SECRET
    assert json.loads(res["redirect-uris"].replace("'", '"')) == CLIENT_REDIRECT_URIS


async def test_list_oauth_clients(oauth_clients: dict[str, str]) -> None:
    assert len(oauth_clients) > 0


async def test_get_client(hydra_unit: Unit, oauth_clients: dict[str, str]) -> None:
    action = await hydra_unit.run_action(
        "get-oauth-client-info",
        **{
            "client-id": oauth_clients["1"],
        },
    )
    res = (await action.wait()).results

    assert json.loads(res["redirect-uris"].replace("'", '"')) == CLIENT_REDIRECT_URIS


async def test_update_client(
    hydra_unit: Unit,
    oauth_clients: dict[str, str],
) -> None:
    redirect_uris = ["https://other.app/oauth/callback"]
    action = await hydra_unit.run_action(
        "update-oauth-client",
        **{
            "client-id": oauth_clients["1"],
            "redirect-uris": redirect_uris,
        },
    )
    res = (await action.wait()).results

    assert json.loads(res["redirect-uris"].replace("'", '"')) == redirect_uris


async def test_get_opaque_access_token(
    ops_test: OpsTest,
    hydra_application: Application,
    oauth_clients: dict[str, str],
    client_credential_request: Callable[[str, str], Awaitable[Response]],
) -> None:
    await hydra_application.set_config({
        "jwt_access_tokens": "false",
    })
    await ops_test.model.wait_for_idle(
        apps=[HYDRA_APP],
        status="active",
        timeout=5 * 60,
    )

    client_id = oauth_clients["1"]
    resp = await client_credential_request(client_id, CLIENT_SECRET)
    assert resp.status_code == 200
    assert resp.json()["access_token"]

    with pytest.raises(jwt.exceptions.DecodeError):
        jwt.decode(
            resp.json()["access_token"],
            algorithms=["RS256"],
            options={"verify_signature": False},
        )


async def test_get_jwt_access_token(
    ops_test: OpsTest,
    hydra_application: Application,
    oauth_clients: dict,
    client_credential_request: Callable[[str, str], Awaitable[Response]],
    jwks_client: jwt.PyJWKClient,
) -> None:
    await hydra_application.set_config({
        "jwt_access_tokens": "true",
    })
    await ops_test.model.wait_for_idle(
        apps=[HYDRA_APP],
        status="active",
        timeout=5 * 60,
    )

    client_id = oauth_clients["1"]
    resp = await client_credential_request(client_id, CLIENT_SECRET)
    assert resp.status_code == 200
    assert resp.json()["access_token"]

    access_token = resp.json()["access_token"]

    signing_key = jwks_client.get_signing_key_from_jwt(access_token)
    decoded = jwt.decode(
        access_token, signing_key.key, algorithms=["RS256"], options={"verify_signature": False}
    )
    assert decoded
    assert decoded["client_id"] == client_id


async def test_revoke_oauth_client_access_tokens(
    hydra_unit: Unit, oauth_clients: dict[str, str]
) -> None:
    client_id = oauth_clients["1"]

    action = await hydra_unit.run_action(
        "revoke-oauth-client-access-tokens",
        **{
            "client-id": client_id,
        },
    )

    res = (await action.wait()).results
    assert res["client-id"] == client_id


async def test_delete_oauth_client(hydra_unit: Unit, oauth_clients: dict[str, str]) -> None:
    client_id = oauth_clients["1"]

    action = await hydra_unit.run_action(
        "delete-oauth-client",
        **{
            "client-id": client_id,
        },
    )

    res = (await action.wait()).results
    assert res["client-id"] == client_id

    action = await hydra_unit.run_action(
        "get-oauth-client-info",
        **{
            "client-id": client_id,
        },
    )
    res = await action.wait()
    assert res.status == "failed"


@pytest.mark.parametrize("get_hydra_jwks", ["public"], indirect=True)
async def test_rotate_keys(
    get_hydra_jwks: Callable[[], Awaitable[Response]], hydra_unit: Unit
) -> None:
    # get original jwks
    jwks = (await get_hydra_jwks()).json()

    # add a new jwk
    action = await hydra_unit.run_action("rotate-key")
    res = (await action.wait()).results
    new_kid = res["new-key-id"]

    # get current jwks
    new_jwks = (await get_hydra_jwks()).json()

    assert any(jwk["kid"] == new_kid for jwk in new_jwks["keys"])
    assert len(new_jwks["keys"]) == len(jwks["keys"]) + 1


async def test_scale_up(
    ops_test: OpsTest,
    hydra_application: Application,
    leader_peer_integration_data: Optional[dict],
    app_integration_data: Callable,
) -> None:
    target_unit_number = 2
    await hydra_application.scale(target_unit_number)

    await ops_test.model.wait_for_idle(
        apps=[HYDRA_APP],
        status="active",
        raise_on_blocked=True,
        timeout=5 * 60,
        wait_for_exact_units=target_unit_number,
    )

    follower_peer_data = await app_integration_data(HYDRA_APP, HYDRA_APP, 1)
    assert follower_peer_data
    assert leader_peer_integration_data == follower_peer_data


async def test_remove_database_integration(
    ops_test: OpsTest, hydra_application: Application
) -> None:
    async with remove_integration(ops_test, DB_APP, DATABASE_INTEGRATION_NAME):
        assert hydra_application.status == "blocked"


async def test_remove_public_route_integration(
    ops_test: OpsTest, hydra_application: Application
) -> None:
    async with remove_integration(ops_test, TRAEFIK_PUBLIC_APP, PUBLIC_ROUTE_INTEGRATION_NAME):
        assert hydra_application.status == "blocked"


async def test_remove_login_ui_integration(
    ops_test: OpsTest, hydra_application: Application
) -> None:
    async with remove_integration(ops_test, LOGIN_UI_APP, LOGIN_UI_INTEGRATION_NAME):
        assert hydra_application.status == "blocked"


async def test_scale_down(ops_test: OpsTest, hydra_application: Application) -> None:
    target_unit_num = 1
    await hydra_application.scale(target_unit_num)

    await ops_test.model.wait_for_idle(
        apps=[HYDRA_APP],
        status="active",
        timeout=5 * 60,
        wait_for_exact_units=target_unit_num,
    )


async def test_get_system_secret(hydra_unit: Unit, oauth_clients: dict[str, str]) -> None:
    global system_secret

    action = await hydra_unit.run_action(
        "get-secret-keys",
        **{
            "type": "system",
        },
    )

    res = (await action.wait()).results
    assert res["system"]
    system_secret = res["system"]


async def test_get_cookie_secret(hydra_unit: Unit, oauth_clients: dict[str, str]) -> None:
    global cookie_secret

    action = await hydra_unit.run_action(
        "get-secret-keys",
        **{
            "type": "cookie",
        },
    )

    res = (await action.wait()).results
    assert res["cookie"]
    cookie_secret = res["cookie"]


@pytest.mark.skip
@pytest.mark.parametrize("get_hydra_jwks", ["public"], indirect=True)
async def test_upgrade(
    ops_test: OpsTest,
    hydra_application: Application,
    local_charm: Path,
    hydra_unit: Unit,
    get_hydra_jwks: Callable[[], Awaitable[Response]],
) -> None:
    # remove the current hydra application
    await ops_test.model.remove_application(
        app_name=HYDRA_APP,
        block_until_done=True,
        destroy_storage=True,
    )

    # deploy the latest hydra application from CharmHub
    await ops_test.model.deploy(
        application_name=HYDRA_APP,
        entity_url="ch:hydra",
        channel="edge",
        series="jammy",
        trust=True,
    )

    # integrate with dependencies
    await integrate_dependencies(ops_test)

    await ops_test.model.wait_for_idle(
        apps=[HYDRA_APP, DB_APP, TRAEFIK_PUBLIC_APP, TRAEFIK_ADMIN_APP],
        raise_on_blocked=False,
        status="active",
        timeout=5 * 60,
    )

    # upgrade the charm
    await hydra_application.refresh(
        path=str(local_charm),
        resources={"oci-image": HYDRA_IMAGE},
    )

    await ops_test.model.wait_for_idle(
        apps=[HYDRA_APP],
        status="active",
        timeout=5 * 60,
    )

    for secret in json.loads(cookie_secret):
        action = await hydra_unit.run_action(
            "add-secret-key",
            **{
                "type": "cookie",
                "key": secret,
            },
        )
        await action.wait()

    for secret in json.loads(system_secret):
        action = await hydra_unit.run_action(
            "add-secret-key",
            **{
                "type": "system",
                "key": secret,
            },
        )
        await action.wait()

    await ops_test.model.wait_for_idle(
        apps=[HYDRA_APP],
        status="active",
        timeout=5 * 60,
    )

    jwks = (await get_hydra_jwks()).json()
    assert "error" not in jwks
