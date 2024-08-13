# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import pytest
from ops.testing import Harness

from constants import (
    COOKIE_SECRET_KEY,
    COOKIE_SECRET_LABEL,
    SYSTEM_SECRET_KEY,
    SYSTEM_SECRET_LABEL,
)
from secret import Secrets


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
