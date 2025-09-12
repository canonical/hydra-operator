# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import datetime
import time
from typing import Optional, ValuesView

from ops import Model, SecretNotFoundError

from configs import ServiceConfigs
from constants import (
    COOKIE_SECRET_KEY,
    COOKIE_SECRET_LABEL,
    COOKIE_SECRET,
    PEER_INTEGRATION_COOKIE_SECRET_KEYS,
    PEER_INTEGRATION_SYSTEM_SECRET_KEYS,
    SYSTEM_SECRET_KEY,
    SYSTEM_SECRET_LABEL,
    SYSTEM_SECRET,
)
from integrations import PeerData


class Secrets:
    """An abstraction of the charm secret management."""

    KEYS = (COOKIE_SECRET_KEY, SYSTEM_SECRET_KEY)
    LABELS = (COOKIE_SECRET_LABEL, SYSTEM_SECRET_LABEL)

    def __init__(self, model: Model) -> None:
        self._model = model

    def __getitem__(self, label: str) -> Optional[dict[str, str]]:
        if label not in self.LABELS:
            return None

        try:
            secret = self._model.get_secret(label=label)
        except SecretNotFoundError:
            return None

        return secret.get_content(refresh=True)

    def __setitem__(self, label: str, content: dict[str, str]) -> None:
        if label not in self.LABELS:
            raise ValueError(f"Invalid label: '{label}'. Valid labels are: {self.LABELS}.")

        try:
            secret = self._model.get_secret(label=label)
        except SecretNotFoundError:
            self._model.app.add_secret(content, label=label)
        else:
            secret.set_content(content)

    def values(self) -> ValuesView:
        secret_contents = {}
        for key, label in zip(self.KEYS, self.LABELS):
            try:
                secret = self._model.get_secret(label=label)
            except SecretNotFoundError:
                return ValuesView({})
            else:
                secret_contents[key] = secret.get_content()

        return secret_contents.values()

    def to_service_configs(self) -> ServiceConfigs:
        return {
            "cookie_secrets": [
                self[COOKIE_SECRET_LABEL][COOKIE_SECRET_KEY],  # type: ignore[index]
            ],
            "system_secrets": [
                self[SYSTEM_SECRET_LABEL][SYSTEM_SECRET_KEY],  # type: ignore[index]
            ],
        }

    @property
    def is_ready(self) -> bool:
        values = self.values()
        return all(values) if values else False


class HydraSecrets:
    """An abstraction of the hydra secret management."""

    def __init__(self, secrets: Secrets) -> None:
        self._secrets = secrets

    def to_service_configs(self) -> ServiceConfigs:
        return {
            "cookie_secrets": self.get_secret_keys(COOKIE_SECRET),
            "system_secrets": self.get_secret_keys(SYSTEM_SECRET),
        }

    def get_secret_keys(self, typ: str) -> list[str]:
        """Returns all the secrets used to encode sensitive data."""
        secret_label = {
            SYSTEM_SECRET: SYSTEM_SECRET_LABEL,
            COOKIE_SECRET: COOKIE_SECRET_LABEL,
        }[typ]
        secrets = self._secrets[secret_label] or {}

        return [secret for _, secret in sorted(secrets.items(), reverse=True)]

    def add_secret_key(self, typ: str, key: str) -> None:
        """Add a new secret key."""
        secret_key, secret_label = {
            SYSTEM_SECRET: (SYSTEM_SECRET_KEY, SYSTEM_SECRET_LABEL),
            COOKIE_SECRET: (COOKIE_SECRET_KEY, COOKIE_SECRET_LABEL),
        }[typ]
        secrets = self._secrets[secret_label] or {}
        secrets[f"{secret_key}{datetime.datetime.fromtimestamp(time.time()).strftime('%Y%m%d%H%M%S')}"] = key
        self._secrets[secret_label] = secrets

    @property
    def is_ready(self) -> bool:
        values = [self.get_secret_keys(SYSTEM_SECRET), self.get_secret_keys(COOKIE_SECRET)]
        return all(values) if values else False
