# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
from typing import Any, Dict

import pytest
import yaml
from charms.hydra.v0.oauth import (
    CLIENT_SECRET_FIELD,
    ClientConfig,
    InvalidClientConfigEvent,
    OAuthInfoChangedEvent,
    OauthProviderConfig,
    OAuthRequirer,
)
from ops import EventBase
from ops.charm import CharmBase
from ops.testing import Context, Relation, Secret
from unit.conftest import create_state

METADATA = """
name: requirer-tester
requires:
  oauth:
    interface: oauth
"""

CLIENT_CONFIG = {
    "redirect_uri": "https://example.oidc.client/callback",
    "scope": "openid email offline_access",
    "grant_types": [
        "authorization_code",
        "refresh_token",
        "client_credentials",
        "urn:ietf:params:oauth:grant-type:device_code",
    ],
    "audience": [],
    "token_endpoint_auth_method": "client_secret_basic",
}


class OAuthRequirerCharm(CharmBase):
    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.config_to_update = None
        client_config = ClientConfig(**CLIENT_CONFIG)
        self.oauth = OAuthRequirer(self, client_config=client_config)

        self.framework.observe(self.on.start, self._on_start)

    def _on_start(self, event: EventBase) -> None:
        if self.config_to_update:
            self.oauth.update_client_config(self.config_to_update)

    @property
    def provider_info(self) -> OauthProviderConfig | None:
        return self.oauth.get_provider_info()

    @property
    def client_secret_content(self) -> dict:
        rel = self.model.get_relation(self.oauth._relation_name)
        assert rel is not None
        client_secret_id = rel.data[rel.app]["client_secret_id"]
        secret = self.oauth.get_client_secret(client_secret_id)
        return secret.get_content()


class InvalidConfigOAuthRequirerCharm(CharmBase):
    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        client_config = ClientConfig(**CLIENT_CONFIG)
        client_config.grant_types = ["invalid_grant_type"]
        self.oauth = OAuthRequirer(self, client_config=client_config)


@pytest.fixture
def context() -> Context:
    return Context(OAuthRequirerCharm, meta=yaml.safe_load(METADATA))


@pytest.fixture
def context_invalid_config() -> Context:
    return Context(InvalidConfigOAuthRequirerCharm, meta=yaml.safe_load(METADATA))


@pytest.fixture()
def provider_info() -> Dict:
    return {
        "authorization_endpoint": "https://example.oidc.com/oauth2/auth",
        "introspection_endpoint": "https://example.oidc.com/admin/oauth2/introspect",
        "issuer_url": "https://example.oidc.com",
        "jwks_endpoint": "https://example.oidc.com/.well-known/jwks.json",
        "scope": "openid profile email phone",
        "token_endpoint": "https://example.oidc.com/oauth2/token",
        "userinfo_endpoint": "https://example.oidc.com/userinfo",
        "jwt_access_token": "False",
    }


def dict_to_relation_data(dic: Dict) -> Dict:
    return {k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in dic.items()}


def test_data_in_relation_bag(context: Context) -> None:
    relation = Relation("oauth")
    state = create_state(leader=True, relations=[relation], containers=[])

    state_out = context.run(context.on.relation_created(relation), state)

    relation_out = state_out.get_relation(relation.id)
    assert relation_out.local_app_data == dict_to_relation_data(CLIENT_CONFIG)


def test_no_event_emitted_when_provider_info_available_but_no_client_id(
    context: Context, provider_info: Dict
) -> None:
    relation = Relation("oauth", remote_app_data=provider_info)
    state = create_state(leader=True, relations=[relation], containers=[])

    context.run(context.on.relation_changed(relation), state)

    # Let's check captured events
    assert not any(
        isinstance(e, (OAuthInfoChangedEvent, InvalidClientConfigEvent))
        for e in context.emitted_events
    )


def test_oauth_info_changed_event_emitted_when_client_created(
    context: Context, provider_info: Dict
) -> None:
    client_secret = "s3cR#T"
    secret_id = "secret:123"
    secret = Secret(id=secret_id, tracked_content={CLIENT_SECRET_FIELD: client_secret})

    remote_data = {"client_id": "client_id", "client_secret_id": secret_id, **provider_info}

    relation = Relation("oauth", remote_app_data=remote_data)
    state = create_state(leader=True, relations=[relation], secrets=[secret], containers=[])

    with context(context.on.relation_changed(relation), state) as mgr:
        mgr.run()
        assert any(isinstance(e, OAuthInfoChangedEvent) for e in context.emitted_events)
        event = next(e for e in context.emitted_events if isinstance(e, OAuthInfoChangedEvent))
        assert event.client_id == "client_id"
        assert event.client_secret_id == secret_id
        assert mgr.charm.client_secret_content == {CLIENT_SECRET_FIELD: client_secret}


def test_get_provider_info_when_data_available(context: Context, provider_info: Dict) -> None:
    relation = Relation("oauth", remote_app_data=provider_info)
    state = create_state(leader=True, relations=[relation], containers=[])

    with context(context.on.relation_changed(relation), state) as mgr:
        mgr.run()
        expected_provider_info = mgr.charm.provider_info

        assert (
            expected_provider_info.authorization_endpoint
            == provider_info["authorization_endpoint"]
        )
        assert (
            expected_provider_info.introspection_endpoint
            == provider_info["introspection_endpoint"]
        )
        assert expected_provider_info.issuer_url == provider_info["issuer_url"]
        assert expected_provider_info.jwks_endpoint == provider_info["jwks_endpoint"]
        assert expected_provider_info.scope == provider_info["scope"]
        assert expected_provider_info.token_endpoint == provider_info["token_endpoint"]
        assert expected_provider_info.userinfo_endpoint == provider_info["userinfo_endpoint"]
        assert expected_provider_info.jwt_access_token == (
            provider_info["jwt_access_token"] == "True"
        )


def test_get_client_credentials_when_data_available(context: Context, provider_info: Dict) -> None:
    client_id = "client_id"
    client_secret = "s3cR#T"
    secret_id = "secret:123"

    secret = Secret(id=secret_id, tracked_content={CLIENT_SECRET_FIELD: client_secret})

    remote_data = dict(client_id=client_id, client_secret_id=secret_id, **provider_info)
    relation = Relation("oauth", remote_app_data=remote_data)

    state = create_state(leader=True, relations=[relation], secrets=[secret], containers=[])

    with context(context.on.relation_changed(relation), state) as mgr:
        mgr.run()
        expected_client_details = mgr.charm.provider_info
        assert expected_client_details.client_id == client_id
        assert expected_client_details.client_secret == client_secret


def test_exception_raised_when_malformed_redirect_url(context: Context) -> None:
    state = create_state(leader=True, containers=[])

    client_config = ClientConfig(**CLIENT_CONFIG)
    client_config.redirect_uri = "malformed-url"

    with context(context.on.start(), state) as mgr:
        mgr.charm.config_to_update = client_config
        # Scenario wraps exceptions in UncaughtCharmError
        with pytest.raises(Exception, match=f"Invalid URL {client_config.redirect_uri}"):
            mgr.run()


def test_warning_when_http_redirect_url(
    context: Context, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    state = create_state(leader=True, containers=[])

    client_config = ClientConfig(**CLIENT_CONFIG)
    client_config.redirect_uri = "http://some.callback"

    with context(context.on.start(), state) as mgr:
        mgr.charm.config_to_update = client_config
        mgr.run()
        assert "Provided Redirect URL uses http scheme. Don't do this in production" in caplog.text


def test_exception_raised_when_invalid_grant_type(context: Context) -> None:
    state = create_state(leader=True, containers=[])

    client_config = ClientConfig(**CLIENT_CONFIG)
    client_config.grant_types = ["authorization_code", "token_exchange"]

    with context(context.on.start(), state) as mgr:
        mgr.charm.config_to_update = client_config
        with pytest.raises(Exception, match="Invalid grant_type"):
            mgr.run()


def test_exception_raised_when_invalid_client_authn_method(context: Context) -> None:
    state = create_state(leader=True, containers=[])

    client_config = ClientConfig(**CLIENT_CONFIG)
    client_config.token_endpoint_auth_method = "private_key_jwt"

    with context(context.on.start(), state) as mgr:
        mgr.charm.config_to_update = client_config
        with pytest.raises(Exception, match="Invalid client auth method"):
            mgr.run()


def test_event_emitted_when_invalid_client_config(context_invalid_config: Context) -> None:
    relation = Relation("oauth")
    state = create_state(leader=True, relations=[relation], containers=[])

    context_invalid_config.run(context_invalid_config.on.relation_created(relation), state)

    assert any(
        isinstance(e, InvalidClientConfigEvent) for e in context_invalid_config.emitted_events
    )


@pytest.mark.xfail(
    reason="We no longer remove clients on relation removal, see https://github.com/canonical/hydra-operator/issues/268"
)
def test_event_deferred_on_relation_broken_when_relation_data_available(
    context: Context,
    provider_info: Dict,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)

    remote_data = dict(client_id="client_id", client_secret_id="s3cR#T", **provider_info)
    relation = Relation("oauth", remote_app_data=remote_data)
    state = create_state(leader=True, relations=[relation], containers=[])

    context.run(context.on.relation_broken(relation), state)

    assert caplog.record_tuples[0][2] == "Relation data still available. Deferring the event"
