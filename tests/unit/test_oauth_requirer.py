# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
from typing import Any, Dict, Generator, List
from unittest.mock import MagicMock

import pytest
from charms.hydra.v0.oauth import (
    CLIENT_SECRET_FIELD,
    ClientConfig,
    ClientConfigError,
    InvalidClientConfigEvent,
    OAuthInfoChangedEvent,
    OAuthRequirer,
)
from ops.charm import CharmBase
from ops.framework import EventBase
from ops.testing import Harness
from pytest_mock import MockerFixture

METADATA = """
name: requirer-tester
requires:
  oauth:
    interface: oauth
"""


@pytest.fixture()
def harness() -> Generator:
    harness = Harness(OAuthRequirerCharm, meta=METADATA)
    harness.set_leader(True)
    harness.begin_with_initial_hooks()
    yield harness
    harness.cleanup()


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
    }


@pytest.fixture()
def mocked_client_is_created(mocker: MockerFixture) -> MagicMock:
    mocked_client_created = mocker.patch(
        "charms.hydra.v0.oauth.OAuthRequirer.is_client_created", return_value=True
    )
    return mocked_client_created


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


def dict_to_relation_data(dic: Dict) -> Dict:
    return {k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in dic.items()}


class OAuthRequirerCharm(CharmBase):
    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        client_config = ClientConfig(**CLIENT_CONFIG)
        self.oauth = OAuthRequirer(self, client_config=client_config)

        self.events: List = []
        self.framework.observe(self.oauth.on.oauth_info_changed, self._record_event)
        self.framework.observe(self.oauth.on.invalid_client_config, self._record_event)

    def _record_event(self, event: EventBase) -> None:
        self.events.append(event)


def test_data_in_relation_bag(harness: Harness) -> None:
    relation_id = harness.add_relation("oauth", "provider")

    relation_data = harness.get_relation_data(relation_id, harness.model.app.name)

    assert relation_data == dict_to_relation_data(CLIENT_CONFIG)


def test_no_event_emitted_when_provider_info_available_but_no_client_id(
    harness: Harness, provider_info: Dict
) -> None:
    relation_id = harness.add_relation("oauth", "provider")
    harness.add_relation_unit(relation_id, "provider/0")
    harness.update_relation_data(
        relation_id,
        "provider",
        provider_info,
    )
    relation_data = harness.get_relation_data(relation_id, harness.model.app.name)
    events = harness.charm.events

    assert relation_data == dict_to_relation_data(CLIENT_CONFIG)
    assert len(events) == 0


def test_oauth_info_changed_event_emitted_when_client_created(
    harness: Harness, provider_info: Dict
) -> None:
    client_secret = "s3cR#T"
    relation_id = harness.add_relation("oauth", "provider")
    harness.add_relation_unit(relation_id, "provider/0")
    harness.update_relation_data(
        relation_id,
        "provider",
        provider_info,
    )

    secret_id = harness.add_model_secret("provider", {CLIENT_SECRET_FIELD: client_secret})
    harness.grant_secret(secret_id, "requirer-tester")
    harness.update_relation_data(
        relation_id,
        "provider",
        {
            "client_id": "client_id",
            "client_secret_id": secret_id,
        },
    )

    assert any(isinstance(event := e, OAuthInfoChangedEvent) for e in harness.charm.events)
    assert event.client_id == "client_id"
    assert event.client_secret_id == secret_id
    secret = harness.charm.oauth.get_client_secret(event.client_secret_id)
    assert secret.get_content() == {"secret": client_secret}


def test_get_provider_info_when_data_available(harness: Harness, provider_info: Dict) -> None:
    relation_id = harness.add_relation("oauth", "provider")
    harness.add_relation_unit(relation_id, "provider/0")
    harness.update_relation_data(
        relation_id,
        "provider",
        provider_info,
    )

    expected_provider_info = harness.charm.oauth.get_provider_info()

    assert expected_provider_info.authorization_endpoint == provider_info["authorization_endpoint"]
    assert expected_provider_info.introspection_endpoint == provider_info["introspection_endpoint"]
    assert expected_provider_info.issuer_url == provider_info["issuer_url"]
    assert expected_provider_info.jwks_endpoint == provider_info["jwks_endpoint"]
    assert expected_provider_info.scope == provider_info["scope"]
    assert expected_provider_info.token_endpoint == provider_info["token_endpoint"]
    assert expected_provider_info.userinfo_endpoint == provider_info["userinfo_endpoint"]


def test_get_client_credentials_when_data_available(harness: Harness, provider_info: Dict) -> None:
    client_id = "client_id"
    client_secret = "s3cR#T"
    relation_id = harness.add_relation("oauth", "provider")
    harness.add_relation_unit(relation_id, "provider/0")
    secret_id = harness.add_model_secret("provider", {CLIENT_SECRET_FIELD: client_secret})
    harness.grant_secret(secret_id, "requirer-tester")

    harness.update_relation_data(
        relation_id,
        "provider",
        dict(client_id=client_id, client_secret_id=secret_id, **provider_info),
    )

    expected_client_details = harness.charm.oauth.get_provider_info()

    assert expected_client_details.client_id == client_id
    assert expected_client_details.client_secret == client_secret


def test_exception_raised_when_malformed_redirect_url(harness: Harness) -> None:
    client_config = ClientConfig(**CLIENT_CONFIG)
    client_config.redirect_uri = "malformed-url"

    with pytest.raises(ClientConfigError, match=f"Invalid URL {client_config.redirect_uri}"):
        harness.charm.oauth.update_client_config(client_config=client_config)


def test_warning_when_http_redirect_url(
    harness: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    client_config = ClientConfig(**CLIENT_CONFIG)
    client_config.redirect_uri = "http://some.callback"

    harness.charm.oauth.update_client_config(client_config=client_config)
    assert "Provided Redirect URL uses http scheme. Don't do this in production" in caplog.text


def test_exception_raised_when_invalid_grant_type(harness: Harness) -> None:
    client_config = ClientConfig(**CLIENT_CONFIG)
    client_config.grant_types = ["authorization_code", "token_exchange"]

    with pytest.raises(ClientConfigError, match="Invalid grant_type"):
        harness.charm.oauth.update_client_config(client_config=client_config)


def test_exception_raised_when_invalid_client_authn_method(harness: Harness) -> None:
    client_config = ClientConfig(**CLIENT_CONFIG)
    client_config.token_endpoint_auth_method = "private_key_jwt"

    with pytest.raises(ClientConfigError, match="Invalid client auth method"):
        harness.charm.oauth.update_client_config(client_config=client_config)


class InvalidConfigOAuthRequirerCharm(CharmBase):
    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        client_config = ClientConfig(**CLIENT_CONFIG)
        client_config.grant_types = ["invalid_grant_type"]
        self.oauth = OAuthRequirer(self, client_config=client_config)

        self.events: List = []
        self.framework.observe(self.oauth.on.oauth_info_changed, self._record_event)
        self.framework.observe(self.oauth.on.invalid_client_config, self._record_event)

    def _record_event(self, event: EventBase) -> None:
        self.events.append(event)


@pytest.fixture()
def harness_invalid_config() -> Generator:
    harness = Harness(InvalidConfigOAuthRequirerCharm, meta=METADATA)
    harness.set_leader(True)
    harness.begin_with_initial_hooks()
    yield harness
    harness.cleanup()


def test_event_emitted_when_invalid_client_config(harness_invalid_config: Harness) -> None:
    harness_invalid_config.add_relation("oauth", "provider")

    assert any(
        isinstance(e, InvalidClientConfigEvent) for e in harness_invalid_config.charm.events
    )


def test_event_deferred_on_relation_broken_when_relation_data_available(
    harness: Harness,
    provider_info: Dict,
    mocked_client_is_created: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    relation_id = harness.add_relation("oauth", "provider")
    harness.add_relation_unit(relation_id, "provider/0")

    harness.update_relation_data(
        relation_id,
        "provider",
        dict(client_id="client_id", client_secret_id="s3cR#T", **provider_info),
    )

    harness.remove_relation(relation_id)

    assert caplog.record_tuples[0][2] == "Relation data still available. Deferring the event"
