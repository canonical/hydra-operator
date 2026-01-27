# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from os.path import join
from typing import Any

import pytest
import yaml
from charms.hydra.v0.oauth import (
    CLIENT_SECRET_FIELD,
    ClientChangedEvent,
    ClientCreatedEvent,
    ClientDeletedEvent,
    OAuthProvider,
)
from ops.charm import CharmBase, RelationCreatedEvent
from ops.testing import Context, Relation, Secret
from unit.conftest import create_state

METADATA = """
name: provider-tester
provides:
  oauth:
    interface: oauth
"""
CLIENT_ID = "client_id"
CLIENT_SECRET = "client_secret"


class OAuthProviderCharm(CharmBase):
    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.oauth = OAuthProvider(self)

        self.framework.observe(self.on.oauth_relation_created, self._on_relation_created)
        self.framework.observe(self.oauth.on.client_created, self._on_client_created)

    def _on_client_created(self, event: ClientCreatedEvent) -> None:
        self.oauth.set_client_credentials_in_relation_data(
            event.relation_id, CLIENT_ID, CLIENT_SECRET
        )

    def _on_relation_created(self, _: RelationCreatedEvent) -> None:
        public_ingress = "https://example.oidc.com"
        self.oauth.set_provider_info_in_relation_data(
            issuer_url=public_ingress,
            authorization_endpoint=join(public_ingress, "oauth2/auth"),
            token_endpoint=join(public_ingress, "oauth2/token"),
            introspection_endpoint=join(public_ingress, "admin/oauth2/introspect"),
            userinfo_endpoint=join(public_ingress, "userinfo"),
            jwks_endpoint=join(public_ingress, ".well-known/jwks.json"),
            scope="openid profile email phone",
        )


@pytest.fixture
def context() -> Context:
    return Context(OAuthProviderCharm, meta=yaml.safe_load(METADATA))


def test_provider_info_in_relation_databag(context: Context) -> None:
    relation = Relation("oauth")
    state = create_state(leader=True, relations=[relation], containers=[])

    state_out = context.run(context.on.relation_created(relation), state)

    relation_out = state_out.get_relation(relation.id)
    relation_data = relation_out.local_app_data
    assert relation_data == {
        "authorization_endpoint": "https://example.oidc.com/oauth2/auth",
        "introspection_endpoint": "https://example.oidc.com/admin/oauth2/introspect",
        "issuer_url": "https://example.oidc.com",
        "jwks_endpoint": "https://example.oidc.com/.well-known/jwks.json",
        "scope": "openid profile email phone",
        "token_endpoint": "https://example.oidc.com/oauth2/token",
        "userinfo_endpoint": "https://example.oidc.com/userinfo",
        "jwt_access_token": "False",
    }


def test_client_credentials_in_relation_databag_when_client_available(context: Context) -> None:
    requirer_data = {
        "redirect_uri": "https://oidc-client.com/callback",
        "scope": "openid email",
        "grant_types": '["authorization_code"]',
        "audience": "[]",
        "token_endpoint_auth_method": "client_secret_basic",
    }

    provider_data = {
        "issuer_url": "https://example.oidc.com",
        "authorization_endpoint": "https://example.oidc.com/oauth2/auth",
        "token_endpoint": "https://example.oidc.com/oauth2/token",
        "introspection_endpoint": "https://example.oidc.com/admin/oauth2/introspect",
        "userinfo_endpoint": "https://example.oidc.com/userinfo",
        "jwks_endpoint": "https://example.oidc.com/.well-known/jwks.json",
        "scope": "openid profile email phone",
    }

    relation = Relation("oauth", remote_app_data=requirer_data, local_app_data=provider_data)
    state = create_state(leader=True, relations=[relation], containers=[])

    state_out = context.run(context.on.relation_changed(relation), state)

    assert any(isinstance(e, ClientCreatedEvent) for e in context.emitted_events)

    relation_out = state_out.get_relation(relation.id)
    relation_data = relation_out.local_app_data
    assert relation_data.get("client_id") == CLIENT_ID
    assert "client_secret_id" in relation_data

    client_secret_id = relation_data["client_secret_id"]
    secret = next(s for s in state_out.secrets if s.id == client_secret_id)
    assert secret.tracked_content[CLIENT_SECRET_FIELD] == CLIENT_SECRET


def test_client_changed_event_emitted_when_client_config_changed(context: Context) -> None:
    redirect_uri = "https://oidc-client.com/callback2"

    requirer_data = {
        "redirect_uri": redirect_uri,
        "scope": "openid email",
        "grant_types": '["authorization_code"]',
        "audience": "[]",
        "token_endpoint_auth_method": "client_secret_basic",
    }

    local_data = {
        "client_id": CLIENT_ID,
        "issuer_url": "https://example.oidc.com",
        "authorization_endpoint": "https://example.oidc.com/oauth2/auth",
        "token_endpoint": "https://example.oidc.com/oauth2/token",
        "introspection_endpoint": "https://example.oidc.com/admin/oauth2/introspect",
        "userinfo_endpoint": "https://example.oidc.com/userinfo",
        "jwks_endpoint": "https://example.oidc.com/.well-known/jwks.json",
        "scope": "openid profile email phone",
    }

    relation = Relation("oauth", remote_app_data=requirer_data, local_app_data=local_data)
    state = create_state(leader=True, relations=[relation], containers=[])

    context.run(context.on.relation_changed(relation), state)

    assert any(
        isinstance(e, ClientChangedEvent) and e.redirect_uri == redirect_uri
        for e in context.emitted_events
    )


@pytest.mark.xfail(
    reason="We no longer remove clients on relation removal, see https://github.com/canonical/hydra-operator/issues/268"
)
def test_client_deleted_event_emitted_when_relation_removed(context: Context) -> None:
    relation = Relation("oauth")
    state = create_state(leader=True, relations=[relation], containers=[])

    context.run(context.on.relation_broken(relation), state)

    assert any(isinstance(e, ClientDeletedEvent) for e in context.emitted_events)


@pytest.mark.xfail(
    reason="We no longer remove clients on relation removal, see https://github.com/canonical/hydra-operator/issues/268"
)
def test_secret_removed_when_relation_removed(context: Context) -> None:
    secret_id = "secret:123"
    secret = Secret(id=secret_id, tracked_content={CLIENT_SECRET_FIELD: "old_secret"})

    local_data = {"client_secret_id": secret_id}
    relation = Relation("oauth", local_app_data=local_data)
    state = create_state(leader=True, relations=[relation], secrets=[secret], containers=[])

    state_out = context.run(context.on.relation_broken(relation), state)

    found_secret = next((s for s in state_out.secrets if s.id == secret_id), None)

    assert found_secret is None
