#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import http
import json
import logging
from pathlib import Path
from typing import Callable, Optional

import jubilant
import jwt
import pytest
import requests
from integration.conftest import integrate_dependencies
from integration.constants import (
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
)
from integration.utils import (
    StatusPredicate,
    all_active,
    and_,
    any_error,
    is_blocked,
    remove_integration,
    unit_number,
)
from yarl import URL

from src.constants import (
    DATABASE_INTEGRATION_NAME,
    LOGIN_UI_INTEGRATION_NAME,
    PUBLIC_ROUTE_INTEGRATION_NAME,
)

logger = logging.getLogger(__name__)


@pytest.mark.setup
def test_build_and_deploy(juju: jubilant.Juju, local_charm: Path) -> None:
    """Build and deploy Hydra."""
    juju.deploy(
        DB_APP,
        channel="14/stable",
        trust=True,
    )
    juju.deploy(
        CA_APP,
        channel="latest/stable",
        trust=True,
    )
    juju.deploy(
        TRAEFIK_CHARM,
        app=TRAEFIK_PUBLIC_APP,
        channel="latest/edge",
        config={"external_hostname": PUBLIC_INGRESS_DOMAIN},
        trust=True,
    )
    juju.deploy(
        TRAEFIK_CHARM,
        app=TRAEFIK_ADMIN_APP,
        channel="latest/stable",
        config={"external_hostname": ADMIN_INGRESS_DOMAIN},
        trust=True,
    )
    juju.deploy(
        LOGIN_UI_APP,
        channel="latest/edge",
        trust=True,
    )

    juju.integrate(f"{TRAEFIK_PUBLIC_APP}:certificates", f"{CA_APP}:certificates")
    juju.integrate(TRAEFIK_PUBLIC_APP, f"{LOGIN_UI_APP}:public-route")

    juju.deploy(
        str(local_charm),
        app=HYDRA_APP,
        resources={"oci-image": HYDRA_IMAGE},
        base="ubuntu@22.04",
        trust=True,
    )

    # Integrate with dependencies
    integrate_dependencies(juju)

    juju.wait(
        ready=all_active(
            HYDRA_APP, DB_APP, CA_APP, TRAEFIK_PUBLIC_APP, TRAEFIK_ADMIN_APP, LOGIN_UI_APP
        ),
        error=any_error(
            HYDRA_APP, DB_APP, CA_APP, TRAEFIK_PUBLIC_APP, TRAEFIK_ADMIN_APP, LOGIN_UI_APP
        ),
        timeout=15 * 60,
    )


def test_peer_integration(
    leader_peer_integration_data: Optional[dict],
    hydra_version: str,
    migration_key: str,
) -> None:
    """Test that peer integration data contains the expected hydra version."""
    assert leader_peer_integration_data
    assert json.loads(leader_peer_integration_data[migration_key]) == hydra_version


def test_login_ui_endpoint_integration(
    login_ui_endpoint_integration_data: Optional[dict],
) -> None:
    """Test that login UI endpoint integration data is present and valid."""
    assert login_ui_endpoint_integration_data
    assert all(login_ui_endpoint_integration_data.values())


@pytest.mark.parametrize("get_hydra_jwks", ["public"], indirect=True)
def test_public_route_integration(
    leader_public_route_integration_data: Optional[dict],
    get_hydra_jwks: Callable[[], requests.Response],
) -> None:
    """Test that public route integration data is present and valid."""
    assert leader_public_route_integration_data
    assert leader_public_route_integration_data["external_host"] == PUBLIC_INGRESS_DOMAIN
    assert leader_public_route_integration_data["scheme"] == "https"

    resp = get_hydra_jwks()
    assert resp.status_code == http.HTTPStatus.OK


def test_openid_configuration_endpoint(get_openid_configuration: requests.Response) -> None:
    """Test that the OpenID metadata endpoint is reachable and valid."""
    base_path = URL(f"https://{PUBLIC_INGRESS_DOMAIN}")
    assert get_openid_configuration.status_code == http.HTTPStatus.OK

    payload = get_openid_configuration.json()
    assert payload["issuer"] == str(base_path)
    assert payload["authorization_endpoint"] == str(base_path / "oauth2/auth")
    assert payload["token_endpoint"] == str(base_path / "oauth2/token")
    assert payload["userinfo_endpoint"] == str(base_path / "userinfo")
    assert payload["jwks_uri"] == str(base_path / ".well-known/jwks.json")


@pytest.mark.parametrize("get_hydra_jwks", ["admin"], indirect=True)
def test_internal_ingress_integration(
    leader_internal_ingress_integration_data: Optional[dict],
    get_admin_clients: requests.Response,
    get_hydra_jwks: Callable[[], requests.Response],
) -> None:
    """Test that internal ingress integration data is present and valid."""
    assert leader_internal_ingress_integration_data
    assert leader_internal_ingress_integration_data["external_host"] == ADMIN_INGRESS_DOMAIN
    assert leader_internal_ingress_integration_data["scheme"] == "http"

    # examine the admin endpoint
    assert get_admin_clients.status_code == http.HTTPStatus.OK

    # examine the public endpoint
    resp = get_hydra_jwks()
    assert resp.status_code == http.HTTPStatus.OK


def test_create_oauth_client_action(juju: jubilant.Juju) -> None:
    """Test creating an OAuth client via action."""
    action = juju.run(
        f"{HYDRA_APP}/0",
        "create-oauth-client",
        params={
            "redirect-uris": CLIENT_REDIRECT_URIS,
            "client-secret": CLIENT_SECRET,
            "grant-types": ["client_credentials"],
        },
    )
    res = action.results

    assert res["client-secret"] == CLIENT_SECRET
    assert json.loads(res["redirect-uris"].replace("'", '"')) == CLIENT_REDIRECT_URIS


def test_list_oauth_clients(oauth_clients: list[dict[str, str]]) -> None:
    """Test listing OAuth clients."""
    assert len(oauth_clients) > 0


def test_get_client(juju: jubilant.Juju, oauth_clients: list[dict[str, str]]) -> None:
    """Test getting an OAuth client info via action."""
    assert len(oauth_clients) > 0
    client_id = oauth_clients[0]["client-id"]

    action = juju.run(
        f"{HYDRA_APP}/0",
        "get-oauth-client-info",
        params={"client-id": client_id},
    )

    assert json.loads(action.results["redirect-uris"].replace("'", '"')) == CLIENT_REDIRECT_URIS


def test_update_client(
    juju: jubilant.Juju,
    oauth_clients: list[dict[str, str]],
) -> None:
    """Test updating an OAuth client via action."""
    redirect_uris = ["https://other.app/oauth/callback"]
    assert len(oauth_clients) > 0
    client_id = oauth_clients[0]["client-id"]

    action = juju.run(
        f"{HYDRA_APP}/0",
        "update-oauth-client",
        params={
            "client-id": client_id,
            "redirect-uris": redirect_uris,
        },
    )

    assert json.loads(action.results["redirect-uris"].replace("'", '"')) == redirect_uris


def test_get_opaque_access_token(
    juju: jubilant.Juju,
    oauth_clients: list[dict[str, str]],
    client_credential_request: Callable[[str, str], requests.Response],
) -> None:
    """Test getting an opaque access token."""
    juju.cli("config", HYDRA_APP, "jwt_access_tokens=false")
    juju.wait(
        ready=all_active(HYDRA_APP),
        error=any_error(HYDRA_APP),
        timeout=5 * 60,
    )

    assert len(oauth_clients) > 0
    client_id = oauth_clients[0]["client-id"]
    resp = client_credential_request(client_id, CLIENT_SECRET)
    assert resp.status_code == 200
    assert resp.json()["access_token"]

    with pytest.raises(jwt.exceptions.DecodeError):
        jwt.decode(
            resp.json()["access_token"],
            algorithms=["RS256"],
            options={"verify_signature": False},
        )


def test_get_jwt_access_token(
    juju: jubilant.Juju,
    oauth_clients: list[dict[str, str]],
    client_credential_request: Callable[[str, str], requests.Response],
    jwks_client: jwt.PyJWKClient,
) -> None:
    """Test getting a JWT access token."""
    juju.cli("config", HYDRA_APP, "jwt_access_tokens=true")
    juju.wait(
        ready=all_active(HYDRA_APP),
        error=any_error(HYDRA_APP),
        timeout=5 * 60,
    )

    assert len(oauth_clients) > 0
    client_id = oauth_clients[0]["client-id"]
    resp = client_credential_request(client_id, CLIENT_SECRET)
    assert resp.status_code == 200
    assert resp.json()["access_token"]

    access_token = resp.json()["access_token"]

    signing_key = jwks_client.get_signing_key_from_jwt(access_token)
    decoded = jwt.decode(
        access_token, signing_key.key, algorithms=["RS256"], options={"verify_signature": False}
    )
    assert decoded
    assert decoded["client_id"] == client_id


def test_revoke_oauth_client_access_tokens(
    juju: jubilant.Juju, oauth_clients: list[dict[str, str]]
) -> None:
    """Test revoking OAuth client access tokens via action."""
    assert len(oauth_clients) > 0
    client_id = oauth_clients[0]["client-id"]

    action = juju.run(
        f"{HYDRA_APP}/0",
        "revoke-oauth-client-access-tokens",
        params={"client-id": client_id},
    )

    assert action.results["client-id"] == client_id


def test_delete_oauth_client(juju: jubilant.Juju, oauth_clients: list[dict[str, str]]) -> None:
    """Test deleting an OAuth client via action."""
    assert len(oauth_clients) > 0
    client_id = oauth_clients[0]["client-id"]

    action = juju.run(
        f"{HYDRA_APP}/0",
        "delete-oauth-client",
        params={"client-id": client_id},
    )
    assert action.results["client-id"] == client_id

    with pytest.raises(jubilant.TaskError) as result:
        juju.run(
            f"{HYDRA_APP}/0",
            "get-oauth-client-info",
            params={"client-id": client_id},
        )

    assert result.value.task.status == "failed"


@pytest.mark.parametrize("get_hydra_jwks", ["public"], indirect=True)
def test_rotate_keys(get_hydra_jwks: Callable[[], requests.Response], juju: jubilant.Juju) -> None:
    """Test rotating JWKs via action."""
    # get original jwks
    jwks = get_hydra_jwks().json()

    # add a new jwk
    action = juju.run(f"{HYDRA_APP}/0", "rotate-key")
    new_kid = action.results["new-key-id"]

    # get current jwks
    new_jwks = get_hydra_jwks().json()

    assert any(jwk["kid"] == new_kid for jwk in new_jwks["keys"])
    assert len(new_jwks["keys"]) == len(jwks["keys"]) + 1


def test_scale_up(
    juju: jubilant.Juju,
    leader_peer_integration_data: Optional[dict],
    app_integration_data: Callable,
) -> None:
    """Test scaling up Hydra and verify peer integration data on new unit."""
    target_unit_number = 2
    juju.cli("scale-application", HYDRA_APP, str(target_unit_number))

    juju.wait(
        ready=and_(
            all_active(HYDRA_APP),
            unit_number(HYDRA_APP, target_unit_number),
        ),
        error=any_error(HYDRA_APP),
        timeout=5 * 60,
    )

    follower_peer_data = app_integration_data(HYDRA_APP, HYDRA_APP, 1)
    assert follower_peer_data
    assert leader_peer_integration_data == follower_peer_data


@pytest.mark.parametrize(
    "remote_app_name,integration_name,is_status",
    [
        (DB_APP, DATABASE_INTEGRATION_NAME, is_blocked),
        (TRAEFIK_PUBLIC_APP, PUBLIC_ROUTE_INTEGRATION_NAME, is_blocked),
        (LOGIN_UI_APP, LOGIN_UI_INTEGRATION_NAME, is_blocked),
    ],
)
def test_remove_integration(
    juju: jubilant.Juju,
    remote_app_name: str,
    integration_name: str,
    is_status: Callable[[str], StatusPredicate],
) -> None:
    """Test removing and re-adding integration."""
    with remove_integration(juju, remote_app_name, integration_name):
        juju.wait(
            ready=is_status(HYDRA_APP),
            error=any_error(HYDRA_APP),
            timeout=10 * 60,
        )
    juju.wait(
        ready=all_active(HYDRA_APP, remote_app_name),
        error=any_error(HYDRA_APP, remote_app_name),
        timeout=10 * 60,
    )


def test_scale_down(juju: jubilant.Juju) -> None:
    """Test scaling down Hydra."""
    target_unit_num = 1
    juju.cli("scale-application", HYDRA_APP, str(target_unit_num))

    juju.wait(
        ready=and_(
            all_active(HYDRA_APP),
            unit_number(HYDRA_APP, target_unit_num),
        ),
        error=any_error(HYDRA_APP),
        timeout=5 * 60,
    )


@pytest.mark.teardown
def test_remove_application(juju: jubilant.Juju) -> None:
    """Test removing the application."""
    juju.remove_application(HYDRA_APP, destroy_storage=True)
    juju.wait(lambda s: HYDRA_APP not in s.apps, timeout=1000)
