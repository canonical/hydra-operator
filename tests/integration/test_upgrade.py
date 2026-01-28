#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import http
import json
from pathlib import Path

import jubilant
import pytest
import requests
from integration.constants import (
    ADMIN_INGRESS_DOMAIN,
    CA_APP,
    DB_APP,
    HYDRA_APP,
    HYDRA_IMAGE,
    LOGIN_UI_APP,
    PUBLIC_INGRESS_DOMAIN,
    TRAEFIK_CHARM,
)
from integration.utils import (
    all_active,
    all_maintenance,
    all_waiting,
    any_error,
    get_unit_address,
    or_,
)

from src.constants import (
    INTERNAL_ROUTE_INTEGRATION_NAME,
    LOGIN_UI_INTEGRATION_NAME,
    PUBLIC_ROUTE_INTEGRATION_NAME,
)


@pytest.mark.upgrade
class TestHydraUpgrade:
    system_secret: list[str]
    cookie_secret: list[str]

    hydra_app_name = "hydra-upgrade"
    postgresql_app_name = "postgresql-upgrade"
    ca_app_name = "self-signed-certificates-upgrade"
    traefik_public_app_name = "traefik-public-upgrade"
    traefik_admin_app_name = "traefik-admin-upgrade"
    login_ui_app_name = "identity-platform-login-ui-operator-upgrade"

    @pytest.fixture(scope="class")
    def secrets(self) -> dict[str, str]:
        """Placeholder fixture for class-level secrets storage."""
        return {}

    def integrate_dependencies(self, juju: jubilant.Juju) -> None:
        juju.integrate(self.hydra_app_name, self.postgresql_app_name)
        juju.integrate(
            f"{self.hydra_app_name}:{PUBLIC_ROUTE_INTEGRATION_NAME}", self.traefik_public_app_name
        )
        juju.integrate(
            f"{self.hydra_app_name}:{INTERNAL_ROUTE_INTEGRATION_NAME}", self.traefik_admin_app_name
        )
        juju.integrate(
            f"{self.hydra_app_name}:{LOGIN_UI_INTEGRATION_NAME}",
            f"{self.login_ui_app_name}:{LOGIN_UI_INTEGRATION_NAME}",
        )

    @pytest.mark.setup
    def test_deploy_hydra_from_charmhub(self, juju: jubilant.Juju) -> None:
        """Deploy the charm-under-test."""
        juju.deploy(
            DB_APP,
            app=self.postgresql_app_name,
            channel="14/stable",
            trust=True,
        )
        juju.deploy(
            CA_APP,
            app=self.ca_app_name,
            channel="latest/stable",
            trust=True,
        )
        juju.deploy(
            TRAEFIK_CHARM,
            app=self.traefik_public_app_name,
            channel="latest/edge",
            config={"external_hostname": PUBLIC_INGRESS_DOMAIN},
            trust=True,
        )
        juju.deploy(
            TRAEFIK_CHARM,
            app=self.traefik_admin_app_name,
            channel="latest/stable",
            config={"external_hostname": ADMIN_INGRESS_DOMAIN},
            trust=True,
        )
        juju.deploy(
            LOGIN_UI_APP,
            app=self.login_ui_app_name,
            channel="latest/edge",
            trust=True,
        )

        juju.integrate(
            f"{self.traefik_public_app_name}:certificates", f"{self.ca_app_name}:certificates"
        )
        juju.integrate(self.traefik_public_app_name, f"{self.login_ui_app_name}:public-route")

        juju.deploy(
            HYDRA_APP,
            app=self.hydra_app_name,
            channel="latest/edge",
            trust=True,
        )
        self.integrate_dependencies(juju)

        juju.wait(
            ready=all_active(
                self.hydra_app_name,
                self.postgresql_app_name,
                self.ca_app_name,
                self.traefik_public_app_name,
                self.traefik_admin_app_name,
                self.login_ui_app_name,
            ),
            error=any_error(
                self.hydra_app_name,
                self.postgresql_app_name,
                self.ca_app_name,
                self.traefik_public_app_name,
                self.traefik_admin_app_name,
                self.login_ui_app_name,
            ),
            timeout=15 * 60,
        )

    def test_upgrade(self, juju: jubilant.Juju, local_charm: Path) -> None:
        """Upgrade to the charm-under-test."""
        juju.refresh(
            self.hydra_app_name,
            path=str(local_charm),
            resources={"oci-image": HYDRA_IMAGE},
        )

        juju.wait(
            ready=or_(
                all_waiting(self.hydra_app_name),
                all_maintenance(self.hydra_app_name)
            ),
            error=any_error(self.hydra_app_name),
            timeout=15 * 60,
        )

        juju.run(
            f"{self.hydra_app_name}/0",
            "run-migration",
        )

        juju.wait(
            ready=all_active(self.hydra_app_name),
            error=any_error(self.hydra_app_name),
            timeout=15 * 60,
        )

    def test_verify_action(self, juju: jubilant.Juju, http_client: requests.Session) -> None:
        """Verify that hydra is functional after the upgrade."""
        address = get_unit_address(juju, app_name=self.traefik_public_app_name)
        url = f"https://{address}/.well-known/jwks.json"

        resp = http_client.get(url)

        assert resp.status_code == http.HTTPStatus.OK

    def test_get_secrets(self, juju: jubilant.Juju, secrets: dict[str, str]) -> None:
        """Get the existing secret keys before deleting Hydra."""
        action = juju.run(
            f"{self.hydra_app_name}/0",
            "get-secret-keys",
            params={"type": "system"},
        )
        secrets["system"] = json.loads(action.results["system"])

        action = juju.run(
            f"{self.hydra_app_name}/0",
            "get-secret-keys",
            params={"type": "cookie"},
        )
        secrets["cookie"] = json.loads(action.results["cookie"])

        assert secrets["system"]
        assert secrets["cookie"]

    def test_restore_secrets(
        self,
        juju: jubilant.Juju,
        local_charm: Path,
        http_client: requests.Session,
        secrets: dict[str, str],
    ) -> None:
        """Restore the secret keys after deleting Hydra."""
        juju.remove_application(self.hydra_app_name)
        juju.wait(lambda s: self.hydra_app_name not in s.apps, timeout=15 * 60)

        juju.deploy(
            str(local_charm),
            app=self.hydra_app_name,
            resources={"oci-image": HYDRA_IMAGE},
            base="ubuntu@22.04",
            trust=True,
        )
        self.integrate_dependencies(juju)

        for secret in secrets["cookie"]:
            juju.run(
                f"{self.hydra_app_name}/0",
                "add-secret-key",
                params={
                    "type": "cookie",
                    "key": secret,
                },
            )

        for secret in secrets["system"]:
            juju.run(
                f"{self.hydra_app_name}/0",
                "add-secret-key",
                params={
                    "type": "system",
                    "key": secret,
                },
            )

        juju.wait(
            ready=all_active(self.hydra_app_name),
            error=any_error(self.hydra_app_name),
            timeout=5 * 60,
        )

        address = get_unit_address(juju, app_name=self.traefik_public_app_name)
        url = f"https://{address}/.well-known/jwks.json"

        resp = http_client.get(url)

        assert resp.status_code == http.HTTPStatus.OK
