# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Optional, ValuesView

from ops import Model, SecretNotFoundError

from configs import ServiceConfigs
from constants import (
    COOKIE_SECRET_KEY,
    COOKIE_SECRET_LABEL,
    SYSTEM_SECRET_KEY,
    SYSTEM_SECRET_LABEL,
)


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

        return secret.get_content()

    def __setitem__(self, label: str, content: dict[str, str]) -> None:
        if label not in self.LABELS:
            raise ValueError(f"Invalid label: '{label}'. Valid labels are: {self.LABELS}.")

        self._model.app.add_secret(content, label=label)

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
