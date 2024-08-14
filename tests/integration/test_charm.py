#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from os.path import join
from pathlib import Path

import jwt
import pytest
import requests
import yaml
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
HYDRA_APP = METADATA["name"]
DB_APP = "postgresql-k8s"
TRAEFIK_CHARM = "traefik-k8s"
TRAEFIK_ADMIN_APP = "traefik-admin"
TRAEFIK_PUBLIC_APP = "traefik-public"
CLIENT_SECRET = "secret"
CLIENT_REDIRECT_URIS = ["https://example.com"]
PUBLIC_TRAEFIK_EXTERNAL_NAME = "public"


async def client_credentials_grant_request(
    ops_test: OpsTest, client_id: str, client_secret: str, scope: str = "openid profile"
) -> requests.Response:
    public_address = await get_unit_address(ops_test, TRAEFIK_PUBLIC_APP, 0)
    url = join(f"http://{public_address}/{ops_test.model.name}-{HYDRA_APP}", "oauth2/token")
    body = {
        "grant_type": "client_credentials",
        "scope": scope,
    }

    return requests.post(
        url,
        data=body,
        auth=(client_id, client_secret),
        verify=False,
    )


async def get_hydra_jwks(ops_test: OpsTest):
    public_address = await get_unit_address(ops_test, TRAEFIK_PUBLIC_APP, 0)

    return requests.get(
        f"http://{public_address}/{ops_test.model.name}-{HYDRA_APP}/.well-known/jwks.json"
    )


async def get_unit_address(ops_test: OpsTest, app_name: str, unit_num: int) -> str:
    """Get private address of a unit."""
    status = await ops_test.model.get_status()  # noqa: F821
    return status["applications"][app_name]["units"][f"{app_name}/{unit_num}"]["address"]


async def get_app_address(ops_test: OpsTest, app_name: str) -> str:
    """Get address of an app."""
    status = await ops_test.model.get_status()  # noqa: F821
    return status["applications"][app_name]["public-address"]


@pytest.mark.skip_if_deployed
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest) -> None:
    """Build hydra and deploy it with required charms and relations."""
    charm = await ops_test.build_charm(".")
    hydra_image_path = METADATA["resources"]["oci-image"]["upstream-source"]

    await ops_test.model.deploy(
        entity_url="postgresql-k8s",
        channel="14/stable",
        series="jammy",
        trust=True,
    )

    await ops_test.model.deploy(
        application_name=HYDRA_APP,
        entity_url=charm,
        resources={"oci-image": hydra_image_path},
        series="jammy",
        trust=True,
    )

    await ops_test.model.integrate(
        HYDRA_APP,
        DB_APP,
    )
    await ops_test.model.deploy(
        TRAEFIK_CHARM,
        application_name=TRAEFIK_PUBLIC_APP,
        channel="latest/edge",
        config={"external_hostname": PUBLIC_TRAEFIK_EXTERNAL_NAME},
        trust=True,
    )
    await ops_test.model.deploy(
        TRAEFIK_CHARM,
        application_name=TRAEFIK_ADMIN_APP,
        channel="latest/edge",
        config={"external_hostname": "admin"},
        trust=True,
    )
    await ops_test.model.wait_for_idle(
        apps=[TRAEFIK_PUBLIC_APP, TRAEFIK_ADMIN_APP],
        status="active",
        raise_on_blocked=True,
        timeout=2500,
    )

    await ops_test.model.integrate(f"{HYDRA_APP}:internal-ingress", TRAEFIK_ADMIN_APP)
    await ops_test.model.integrate(f"{HYDRA_APP}:public-ingress", TRAEFIK_PUBLIC_APP)

    await ops_test.model.wait_for_idle(
        apps=[HYDRA_APP, DB_APP],
        raise_on_blocked=False,
        status="active",
        timeout=2500,
    )


async def test_has_public_ingress(ops_test: OpsTest) -> None:
    resp = await get_hydra_jwks(ops_test)

    assert resp.status_code == 200


async def test_has_internal_ingress(ops_test: OpsTest) -> None:
    # Get the traefik address and try to reach kratos
    internal_address = await get_unit_address(ops_test, TRAEFIK_ADMIN_APP, 0)

    # test admin endpoint
    assert (
        requests.get(
            f"http://{internal_address}/{ops_test.model.name}-{HYDRA_APP}/admin/clients"
        ).status_code
        == 200
    )
    # test public endpoint
    assert (
        requests.get(
            f"http://{internal_address}/{ops_test.model.name}-{HYDRA_APP}/.well-known/jwks.json"
        ).status_code
        == 200
    )


async def test_openid_configuration_endpoint(ops_test: OpsTest) -> None:
    # Get the traefik address and try to reach hydra
    public_address = await get_unit_address(ops_test, TRAEFIK_PUBLIC_APP, 0)
    base_path = f"https://{PUBLIC_TRAEFIK_EXTERNAL_NAME}/{ops_test.model.name}-{HYDRA_APP}"

    # TODO: We use the "http" endpoint to make requests to hydra, because the
    # strip-prefix for https fix is not yet release to the traefik stable channel.
    # Switch to https once that is released.
    resp = requests.get(
        f"http://{public_address}/{ops_test.model.name}-{HYDRA_APP}/.well-known/openid-configuration"
    )

    assert resp.status_code == 200

    data = resp.json()

    assert data["issuer"] == base_path
    assert data["authorization_endpoint"] == join(base_path, "oauth2/auth")
    assert data["token_endpoint"] == join(base_path, "oauth2/token")
    assert data["userinfo_endpoint"] == join(base_path, "userinfo")
    assert data["jwks_uri"] == join(base_path, ".well-known/jwks.json")


@pytest.mark.abort_on_fail
async def test_create_client_action(ops_test: OpsTest) -> None:
    action = (
        await ops_test.model.applications[HYDRA_APP]
        .units[0]
        .run_action(
            "create-oauth-client",
            **{
                "redirect-uris": CLIENT_REDIRECT_URIS,
                "client-secret": CLIENT_SECRET,
                "grant-types": ["client_credentials"],
            },
        )
    )
    res = (await action.wait()).results

    assert res["client-secret"] == CLIENT_SECRET
    assert res["redirect-uris"] == "https://example.com"


async def test_list_client(ops_test: OpsTest) -> None:
    action = (
        await ops_test.model.applications[HYDRA_APP]
        .units[0]
        .run_action(
            "list-oauth-clients",
        )
    )
    res = (await action.wait()).results

    assert len(res) > 0


async def test_get_opaque_access_token(ops_test: OpsTest) -> None:
    await ops_test.model.applications[HYDRA_APP].set_config({
        "jwt_access_tokens": "false",
    })

    await ops_test.model.wait_for_idle(
        apps=[HYDRA_APP],
        status="active",
        timeout=1000,
    )

    action = (
        await ops_test.model.applications[HYDRA_APP]
        .units[0]
        .run_action(
            "list-oauth-clients",
        )
    )
    res = (await action.wait()).results
    client_id = res["0"]

    resp = await client_credentials_grant_request(
        ops_test,
        client_id,
        CLIENT_SECRET,
    )

    assert resp.status_code == 200
    assert resp.json()["access_token"]

    with pytest.raises(jwt.exceptions.DecodeError):
        jwt.decode(resp.json()["access_token"], algorithms=["RS256"], verify=False)


async def test_get_jwt_access_token(ops_test: OpsTest) -> None:
    await ops_test.model.applications[HYDRA_APP].set_config({
        "jwt_access_tokens": "true",
    })

    await ops_test.model.wait_for_idle(
        apps=[HYDRA_APP],
        status="active",
        timeout=1000,
    )

    action = (
        await ops_test.model.applications[HYDRA_APP]
        .units[0]
        .run_action(
            "list-oauth-clients",
        )
    )
    res = (await action.wait()).results
    client_id = res["0"]

    resp = await client_credentials_grant_request(
        ops_test,
        client_id,
        CLIENT_SECRET,
    )

    assert resp.status_code == 200
    assert resp.json()["access_token"]

    token = resp.json()["access_token"]

    public_address = await get_unit_address(ops_test, TRAEFIK_PUBLIC_APP, 0)
    jwks_client = jwt.PyJWKClient(
        f"http://{public_address}/{ops_test.model.name}-{HYDRA_APP}/.well-known/jwks.json",
    )
    signing_key = jwks_client.get_signing_key_from_jwt(token)

    assert jwt.decode(token, signing_key.key, algorithms=["RS256"])


async def test_get_client(ops_test: OpsTest) -> None:
    action = (
        await ops_test.model.applications[HYDRA_APP]
        .units[0]
        .run_action(
            "list-oauth-clients",
        )
    )
    res = (await action.wait()).results
    client_id = res["0"]

    action = (
        await ops_test.model.applications[HYDRA_APP]
        .units[0]
        .run_action(
            "get-oauth-client-info",
            **{
                "client-id": client_id,
            },
        )
    )
    res = (await action.wait()).results

    assert res["redirect-uris"] == " ,".join(CLIENT_REDIRECT_URIS)


async def test_update_client(ops_test: OpsTest) -> None:
    action = (
        await ops_test.model.applications[HYDRA_APP]
        .units[0]
        .run_action(
            "list-oauth-clients",
        )
    )
    res = (await action.wait()).results
    client_id = res["0"]

    redirect_uris = ["https://other.app/oauth/callback"]
    action = (
        await ops_test.model.applications[HYDRA_APP]
        .units[0]
        .run_action(
            "update-oauth-client",
            **{
                "client-id": client_id,
                "redirect-uris": redirect_uris,
            },
        )
    )
    res = (await action.wait()).results

    assert res["redirect-uris"] == " ,".join(redirect_uris)


async def test_revoke_access_tokens_client(ops_test: OpsTest) -> None:
    action = (
        await ops_test.model.applications[HYDRA_APP]
        .units[0]
        .run_action(
            "list-oauth-clients",
        )
    )
    res = (await action.wait()).results
    client_id = res["0"]

    action = (
        await ops_test.model.applications[HYDRA_APP]
        .units[0]
        .run_action(
            "revoke-oauth-client-access-tokens",
            **{
                "client-id": client_id,
            },
        )
    )
    res = (await action.wait()).results

    # TODO: Test that tokens are actually deleted?
    assert res["client-id"] == client_id


async def test_delete_client(ops_test: OpsTest) -> None:
    action = (
        await ops_test.model.applications[HYDRA_APP]
        .units[0]
        .run_action(
            "list-oauth-clients",
        )
    )
    res = (await action.wait()).results
    client_id = res["0"]

    action = (
        await ops_test.model.applications[HYDRA_APP]
        .units[0]
        .run_action(
            "delete-oauth-client",
            **{
                "client-id": client_id,
            },
        )
    )
    res = (await action.wait()).results

    assert res["client-id"] == client_id

    action = (
        await ops_test.model.applications[HYDRA_APP]
        .units[0]
        .run_action(
            "get-oauth-client-info",
            **{
                "client-id": client_id,
            },
        )
    )
    res = await action.wait()

    assert res.status == "failed"
    assert res.data["message"] == f"No such client: {client_id}"


async def test_rotate_keys(ops_test: OpsTest) -> None:
    jwks = await get_hydra_jwks(ops_test)

    action = (
        await ops_test.model.applications[HYDRA_APP]
        .units[0]
        .run_action(
            "rotate-key",
        )
    )
    res = (await action.wait()).results

    new_kid = res["new-key-id"]
    new_jwks = await get_hydra_jwks(ops_test)

    assert any(jwk["kid"] == new_kid for jwk in new_jwks.json()["keys"])
    assert len(new_jwks.json()["keys"]) == len(jwks.json()["keys"]) + 1


async def test_hydra_scale_up(ops_test: OpsTest) -> None:
    """Check that hydra works after it is scaled up."""
    app = ops_test.model.applications[HYDRA_APP]

    await app.scale(3)

    await ops_test.model.wait_for_idle(
        apps=[HYDRA_APP],
        status="active",
        raise_on_blocked=True,
        timeout=1000,
        wait_for_exact_units=3,
    )


async def test_hydra_scale_down(ops_test: OpsTest) -> None:
    """Check that hydra works after it is scaled down."""
    app = ops_test.model.applications[HYDRA_APP]

    await app.scale(1)

    await ops_test.model.wait_for_idle(
        apps=[HYDRA_APP],
        status="active",
        timeout=1000,
    )
