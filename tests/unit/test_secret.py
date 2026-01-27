# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock

import pytest
from ops import Model, Secret, SecretNotFoundError

from constants import (
    COOKIE_SECRET_KEY,
    COOKIE_SECRET_LABEL,
    SYSTEM_SECRET,
    SYSTEM_SECRET_KEY,
    SYSTEM_SECRET_LABEL,
)
from secret import HydraSecrets, Secrets


class TestSecrets:
    @pytest.fixture
    def mock_model(self) -> MagicMock:
        return MagicMock(spec=Model)

    @pytest.fixture
    def mock_secret(self) -> MagicMock:
        return MagicMock(spec=Secret)

    @pytest.fixture
    def secrets(self, mock_model: MagicMock) -> Secrets:
        return Secrets(mock_model)

    def test_get(self, mock_model: MagicMock, mock_secret: MagicMock, secrets: Secrets) -> None:
        mock_secret.get_content.return_value = {COOKIE_SECRET_KEY: "cookie"}
        mock_model.get_secret.return_value = mock_secret

        content = secrets[COOKIE_SECRET_LABEL]

        assert content == {COOKIE_SECRET_KEY: "cookie"}
        mock_model.get_secret.assert_called_with(label=COOKIE_SECRET_LABEL)

    def test_get_with_wrong_label(self, mock_model: MagicMock, secrets: Secrets) -> None:
        content = secrets["wrong_label"]

        assert content is None
        mock_model.get_secret.assert_not_called()

    def test_get_with_secret_not_found(self, mock_model: MagicMock, secrets: Secrets) -> None:
        mock_model.get_secret.side_effect = SecretNotFoundError

        content = secrets[SYSTEM_SECRET_LABEL]

        assert content is None

    def test_set_new_secret(self, mock_model: MagicMock, secrets: Secrets) -> None:
        # Simulate secret not found first
        mock_model.get_secret.side_effect = SecretNotFoundError

        secrets[SYSTEM_SECRET_LABEL] = {SYSTEM_SECRET_KEY: "system"}

        mock_model.app.add_secret.assert_called_once_with(
            {SYSTEM_SECRET_KEY: "system"}, label=SYSTEM_SECRET_LABEL
        )

    def test_set_update_existing_secret(
        self, mock_model: MagicMock, mock_secret: MagicMock, secrets: Secrets
    ) -> None:
        mock_model.get_secret.return_value = mock_secret

        secrets[SYSTEM_SECRET_LABEL] = {SYSTEM_SECRET_KEY: "new_value"}

        mock_secret.set_content.assert_called_once_with({SYSTEM_SECRET_KEY: "new_value"})

    def test_set_with_wrong_label(self, secrets: Secrets) -> None:
        with pytest.raises(ValueError):
            secrets["wrong_label"] = {SYSTEM_SECRET_KEY: "system"}

    def test_values(self, mock_model: MagicMock, mock_secret: MagicMock, secrets: Secrets) -> None:
        mock_cookie_secret = MagicMock(spec=Secret)
        mock_cookie_secret.get_content.return_value = {COOKIE_SECRET_KEY: "cookie"}

        mock_system_secret = MagicMock(spec=Secret)
        mock_system_secret.get_content.return_value = {SYSTEM_SECRET_KEY: "system"}

        # Define side effects for get_secret based on label argument
        def get_secret_side_effect(label: str) -> MagicMock:
            if label == COOKIE_SECRET_LABEL:
                return mock_cookie_secret
            if label == SYSTEM_SECRET_LABEL:
                return mock_system_secret
            raise SecretNotFoundError

        mock_model.get_secret.side_effect = get_secret_side_effect

        values = list(secrets.values())

        assert {COOKIE_SECRET_KEY: "cookie"} in values
        assert {SYSTEM_SECRET_KEY: "system"} in values
        assert len(values) == 2

    def test_values_missing_secret(self, mock_model: MagicMock, secrets: Secrets) -> None:
        mock_model.get_secret.side_effect = SecretNotFoundError

        values = list(secrets.values())

        assert len(values) == 0

    def test_is_ready_true(
        self, mock_model: MagicMock, mock_secret: MagicMock, secrets: Secrets
    ) -> None:
        mock_model.get_secret.return_value = mock_secret

        assert secrets.is_ready is True

    def test_is_ready_false(self, mock_model: MagicMock, secrets: Secrets) -> None:
        mock_model.get_secret.side_effect = SecretNotFoundError

        assert secrets.is_ready is False


class TestHydraSecrets:
    @pytest.fixture
    def mock_secrets(self) -> MagicMock:
        return MagicMock(spec=Secrets)

    @pytest.fixture
    def hydra_secrets(self, mock_secrets: MagicMock) -> HydraSecrets:
        return HydraSecrets(mock_secrets)

    def test_to_service_configs(
        self, hydra_secrets: HydraSecrets, mock_secrets: MagicMock
    ) -> None:
        # Setup mock dictionary behavior
        secrets_data = {
            SYSTEM_SECRET_LABEL: {"key1": "val1"},
            COOKIE_SECRET_LABEL: {"key2": "val2"},
        }
        mock_secrets.__getitem__.side_effect = secrets_data.get

        configs = hydra_secrets.to_service_configs()

        assert "cookie_secrets" in configs
        assert "system_secrets" in configs

    def test_add_secret_key(self, hydra_secrets: HydraSecrets, mock_secrets: MagicMock) -> None:
        # Simulate __getitem__ returning an empty dict (which is falsy)
        mock_secrets.__getitem__.return_value = {}

        hydra_secrets.add_secret_key(SYSTEM_SECRET, "new_key")

        # Verify setitem was called with the new content
        mock_secrets.__setitem__.assert_called_once()

        call_args = mock_secrets.__setitem__.call_args
        label, content = call_args[0]

        assert label == SYSTEM_SECRET_LABEL
        assert len(content) == 1
        assert list(content.values())[0] == "new_key"
