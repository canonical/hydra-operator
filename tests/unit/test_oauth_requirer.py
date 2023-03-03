# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import pytest
from charms.hydra.v0.oauth import (
    CLIENT_SECRET_FIELD,
    ClientConfig,
    ClientCredentialsChangedEvent,
    OAuthRequirer,
    ProviderConfigChangedEvent,
    _load_data,
)
from ops.charm import CharmBase
from ops.testing import Harness

METADATA = """
name: requirer-tester
requires:
  oauth:
    interface: oauth
"""


@pytest.fixture()
def harness():
    harness = Harness(OAuthRequirerCharm, meta=METADATA)
    harness.set_leader(True)
    harness.begin_with_initial_hooks()
    yield harness
    harness.cleanup()


CLIENT_CONFIG = {
    "redirect_uri": "https://example.oidc.client/callback",
    "scope": "openid email offline_access",
    "grant_types": ["authorization_code", "refresh_token"],
    "audience": [],
    "token_endpoint_auth_method": "client_secret_basic",
}


class OAuthRequirerCharm(CharmBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        client_config = ClientConfig(**CLIENT_CONFIG)
        self.oauth = OAuthRequirer(self, client_config=client_config)

        self.events = []
        self.framework.observe(self.oauth.on.client_credentials_changed, self._record_event)
        self.framework.observe(self.oauth.on.provider_config_changed, self._record_event)

    def _record_event(self, event):
        self.events.append(event)


def test_data_in_relation_bag_on_joined(harness):
    relation_id = harness.add_relation("oauth", "provider")

    relation_data = harness.get_relation_data(relation_id, harness.model.app.name)

    assert _load_data(relation_data) == CLIENT_CONFIG


def test_client_credentials_changed_emitted_on_client_creation(harness):
    relation_id = harness.add_relation("oauth", "provider")
    harness.add_relation_unit(relation_id, "provider/0")
    secret_id = harness.add_model_secret("provider", {CLIENT_SECRET_FIELD: "s3cR#T"})
    harness.grant_secret(secret_id, "requirer-tester")
    harness.update_relation_data(
        relation_id,
        "provider",
        {
            "authorization_endpoint": "https://example.oidc.com/oauth2/auth",
            "introspection_endpoint": "https://example.oidc.com/admin/oauth2/introspect",
            "issuer_url": "https://example.oidc.com",
            "jwks_endpoint": "https://example.oidc.com/.well-known/jwks.json",
            "scope": "openid profile email phone",
            "token_endpoint": "https://example.oidc.com/oauth2/token",
            "userinfo_endpoint": "https://example.oidc.com/userinfo",
            "client_id": "client_id",
            "client_secret_id": secret_id,
        },
    )
    relation_data = harness.get_relation_data(relation_id, harness.model.app.name)
    events = harness.charm.events

    assert _load_data(relation_data) == CLIENT_CONFIG
    assert len(events) == 1

    event = events[0]

    assert isinstance(event, ClientCredentialsChangedEvent)
    assert event.client_id == "client_id"
    assert event.client_secret_id == secret_id


def test_provider_endpoints_changed_emitted(harness):
    relation_id = harness.add_relation("oauth", "provider")
    harness.add_relation_unit(relation_id, "provider/0")
    harness.update_relation_data(
        relation_id,
        "provider",
        {
            "authorization_endpoint": "https://example.oidc.com/oauth2/auth",
            "introspection_endpoint": "https://example.oidc.com/admin/oauth2/introspect",
            "issuer_url": "https://example.oidc.com",
            "jwks_endpoint": "https://example.oidc.com/.well-known/jwks.json",
            "scope": "openid profile email phone",
            "token_endpoint": "https://example.oidc.com/oauth2/token",
            "userinfo_endpoint": "https://example.oidc.com/userinfo",
        },
    )
    relation_data = harness.get_relation_data(relation_id, harness.model.app.name)
    events = harness.charm.events

    assert _load_data(relation_data) == CLIENT_CONFIG
    assert len(events) == 1

    event = events[0]

    assert isinstance(event, ProviderConfigChangedEvent)
    assert harness.charm.oauth.get_provider_info() == {
        "authorization_endpoint": "https://example.oidc.com/oauth2/auth",
        "introspection_endpoint": "https://example.oidc.com/admin/oauth2/introspect",
        "issuer_url": "https://example.oidc.com",
        "jwks_endpoint": "https://example.oidc.com/.well-known/jwks.json",
        "scope": "openid profile email phone",
        "token_endpoint": "https://example.oidc.com/oauth2/token",
        "userinfo_endpoint": "https://example.oidc.com/userinfo",
    }
