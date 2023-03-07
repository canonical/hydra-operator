# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from os.path import join

import pytest
from charms.hydra.v0.oauth import (
    CLIENT_SECRET_FIELD,
    ClientChangedEvent,
    ClientCreatedEvent,
    ClientDeletedEvent,
    OAuthProvider,
)
from ops.charm import CharmBase
from ops.testing import Harness

METADATA = """
name: provider-tester
provides:
  oauth:
    interface: oauth
"""
CLIENT_ID = "client_id"
CLIENT_SECRET = "client_secret"


class OAuthProviderCharm(CharmBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self.oauth = OAuthProvider(self)
        self.events = []

        self.framework.observe(self.on.oauth_relation_created, self._on_relation_created)
        self.framework.observe(self.oauth.on.client_created, self._on_client_created)
        self.framework.observe(self.oauth.on.client_created, self._record_event)
        self.framework.observe(self.oauth.on.client_changed, self._record_event)
        self.framework.observe(self.oauth.on.client_deleted, self._record_event)

    def _on_client_created(self, event):
        self.oauth.set_client_credentials_in_relation_data(
            event.relation_id, CLIENT_ID, CLIENT_SECRET
        )

    def _on_relation_created(self, _):
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

    def _record_event(self, event):
        self.events.append(event)


@pytest.fixture()
def harness():
    harness = Harness(OAuthProviderCharm, meta=METADATA)
    harness.set_leader(True)
    harness.begin()
    yield harness
    harness.cleanup()


def test_provider_info_in_relation_databag(harness):
    relation_id = harness.add_relation("oauth", "requirer")
    relation_data = harness.get_relation_data(relation_id, harness.model.app.name)

    assert relation_data == {
        "authorization_endpoint": "https://example.oidc.com/oauth2/auth",
        "introspection_endpoint": "https://example.oidc.com/admin/oauth2/introspect",
        "issuer_url": "https://example.oidc.com",
        "jwks_endpoint": "https://example.oidc.com/.well-known/jwks.json",
        "scope": "openid profile email phone",
        "token_endpoint": "https://example.oidc.com/oauth2/token",
        "userinfo_endpoint": "https://example.oidc.com/userinfo",
    }


def test_client_credentials_in_relation_databag(harness):
    relation_id = harness.add_relation("oauth", "requirer")
    harness.add_relation_unit(relation_id, "requirer/0")
    harness.update_relation_data(
        relation_id,
        "requirer",
        {
            "redirect_uri": "https://oidc-client.com/callback",
            "scope": "openid email",
            "grant_types": '["authorization_code"]',
            "audience": "[]",
            "token_endpoint_auth_method": "client_secret_basic",
        },
    )
    relation_data = harness.get_relation_data(relation_id, harness.model.app.name)

    client_secret_id = relation_data.pop("client_secret_id")
    secret = harness.model.get_secret(id=client_secret_id)

    assert len(harness.charm.events) == 1
    assert isinstance(harness.charm.events[0], ClientCreatedEvent)
    assert secret.get_content()[CLIENT_SECRET_FIELD] == CLIENT_SECRET
    assert relation_data == {
        "authorization_endpoint": "https://example.oidc.com/oauth2/auth",
        "introspection_endpoint": "https://example.oidc.com/admin/oauth2/introspect",
        "issuer_url": "https://example.oidc.com",
        "jwks_endpoint": "https://example.oidc.com/.well-known/jwks.json",
        "scope": "openid profile email phone",
        "token_endpoint": "https://example.oidc.com/oauth2/token",
        "userinfo_endpoint": "https://example.oidc.com/userinfo",
        "client_id": CLIENT_ID,
    }


def test_client_changed(harness):
    relation_id = harness.add_relation("oauth", "requirer")
    harness.add_relation_unit(relation_id, "requirer/0")
    harness.update_relation_data(
        relation_id,
        "requirer",
        {
            "redirect_uri": "https://oidc-client.com/callback",
            "scope": "openid email",
            "grant_types": '["authorization_code"]',
            "audience": "[]",
            "token_endpoint_auth_method": "client_secret_basic",
        },
    )
    assert len(harness.charm.events) == 1
    assert isinstance(harness.charm.events[0], ClientCreatedEvent)

    redirect_uri = "https://oidc-client.com/callback2"
    harness.update_relation_data(
        relation_id,
        "requirer",
        {
            "redirect_uri": redirect_uri,
            "scope": "openid email",
            "grant_types": '["authorization_code"]',
            "audience": "[]",
            "token_endpoint_auth_method": "client_secret_basic",
        },
    )

    assert len(harness.charm.events) == 2
    assert isinstance(harness.charm.events[1], ClientChangedEvent)
    assert harness.charm.events[1].redirect_uri == redirect_uri


def test_client_config_deleted(harness):
    relation_id = harness.add_relation("oauth", "requirer")
    harness.add_relation_unit(relation_id, "requirer/0")
    harness.update_relation_data(
        relation_id,
        "requirer",
        {
            "redirect_uri": "https://oidc-client.com/callback",
            "scope": "openid email",
            "grant_types": '["authorization_code"]',
            "audience": "[]",
            "token_endpoint_auth_method": "client_secret_basic",
        },
    )
    assert len(harness.charm.events) == 1
    assert isinstance(harness.charm.events[0], ClientCreatedEvent)

    harness.remove_relation(relation_id)

    assert len(harness.charm.events) == 2
    assert isinstance(harness.charm.events[1], ClientDeletedEvent)
