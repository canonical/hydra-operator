# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import pytest
from ops.testing import Harness

from constants import (
    COOKIE_SECRET_KEY,
    COOKIE_SECRET_LABEL,
    PEER_INTEGRATION_COOKIE_SECRET_KEYS,
    PEER_INTEGRATION_SYSTEM_SECRET_KEYS,
    SYSTEM_SECRET_KEY,
    SYSTEM_SECRET_LABEL,
)
from integrations import PeerData
from secret import HydraSecrets, Secrets


class TestSecrets:
    @pytest.fixture
    def secrets(self, harness: Harness) -> Secrets:
        return Secrets(harness.model)

    @pytest.fixture
    def add_secrets(self, harness: Harness) -> None:
        harness.model.app.add_secret({COOKIE_SECRET_KEY: "cookie"}, label=COOKIE_SECRET_LABEL)
        harness.model.app.add_secret({SYSTEM_SECRET_KEY: "system"}, label=SYSTEM_SECRET_LABEL)

    def test_get(self, secrets: Secrets, add_secrets: None) -> None:
        content = secrets[COOKIE_SECRET_LABEL]
        assert content == {COOKIE_SECRET_KEY: "cookie"}

    def test_get_with_wrong_label(self, secrets: Secrets) -> None:
        content = secrets["wrong_label"]
        assert content is None

    def test_get_with_secret_not_found(self, secrets: Secrets) -> None:
        content = secrets[SYSTEM_SECRET_LABEL]
        assert content is None

    def test_set(self, secrets: Secrets) -> None:
        secrets[SYSTEM_SECRET_LABEL] = {SYSTEM_SECRET_KEY: "system"}
        assert secrets[SYSTEM_SECRET_LABEL] == {SYSTEM_SECRET_KEY: "system"}

    def test_set_with_wrong_label(self, secrets: Secrets) -> None:
        with pytest.raises(ValueError):
            secrets["wrong_label"] = {SYSTEM_SECRET_KEY: "system"}

    def test_values(self, secrets: Secrets, add_secrets: None) -> None:
        assert tuple(secrets.values()) == (
            {COOKIE_SECRET_KEY: "cookie"},
            {SYSTEM_SECRET_KEY: "system"},
        )

    def test_values_with_missing_secret(self, secrets: Secrets) -> None:
        assert not secrets.values()

    def test_to_service_configs(self, secrets: Secrets, add_secrets: None) -> None:
        assert secrets.to_service_configs() == {
            "cookie_secrets": ["cookie"],
            "system_secrets": ["system"],
        }

    def test_is_ready(self, secrets: Secrets, add_secrets: None) -> None:
        assert secrets.is_ready is True

    def test_is_ready_with_missing_secret(self, secrets: Secrets) -> None:
        assert secrets.is_ready is False


class TestHydraSecrets:
    @pytest.fixture
    def secrets(self, harness: Harness) -> HydraSecrets:
        return HydraSecrets(Secrets(harness.model))

    @pytest.fixture
    def add_secrets(self, harness: Harness) -> None:
        harness.model.app.add_secret({COOKIE_SECRET_KEY: "old_cookie", COOKIE_SECRET_KEY+"1": "new_cookie"}, label=COOKIE_SECRET_LABEL)
        harness.model.app.add_secret({SYSTEM_SECRET_KEY: "old_system", SYSTEM_SECRET_KEY+"1": "new_system"}, label=SYSTEM_SECRET_LABEL)

    def test_get_secret_keys(self, secrets: HydraSecrets, add_secrets: None) -> None:
        content = secrets.get_secret_keys("cookie")
        assert content == ["new_cookie", "old_cookie"]

    def test_get_with_wrong_type(self, secrets: HydraSecrets) -> None:
        with pytest.raises(KeyError):
            secrets.get_secret_keys("cooki")

    def test_get_with_secret_not_found(self, secrets: HydraSecrets) -> None:
        content = secrets.get_secret_keys("cookie")
        assert content == []

    def test_set(self, secrets: HydraSecrets) -> None:
        secrets.add_secret_key("cookie", "cookie")

        assert secrets.get_secret_keys("cookie") == ["cookie"]

    def test_set_with_wrong_label(self, secrets: HydraSecrets) -> None:
        with pytest.raises(KeyError):
            secrets.add_secret_key("cooki", "cookie")

    def test_to_service_configs(self, secrets: HydraSecrets, add_secrets: None) -> None:
        assert secrets.to_service_configs() == {
            "cookie_secrets": ["new_cookie", "old_cookie"],
            "system_secrets": ["new_system", "old_system"],
        }

    def test_is_ready(self, secrets: HydraSecrets, add_secrets: None) -> None:
        assert secrets.is_ready is True

    def test_is_ready_with_missing_secret(self, secrets: HydraSecrets) -> None:
        assert secrets.is_ready is False
