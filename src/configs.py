# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from collections import ChainMap
from typing import Any, Mapping, Optional, Protocol, TypeAlias

from jinja2 import Template
from ops import ConfigData, Container, Model, SecretNotFoundError
from ops.pebble import PathError
from typing_extensions import Self

from constants import CONFIG_FILE_NAME, DEFAULT_OAUTH_SCOPES
from env_vars import EnvVars
from exceptions import InvalidHydraConfig

ServiceConfigs: TypeAlias = Mapping[str, Any]


class ServiceConfigSource(Protocol):
    """An interface enforcing the contribution to workload service configs."""

    def to_service_configs(self) -> ServiceConfigs:
        pass


class CharmConfig:
    """A class representing the data source of charm configurations."""

    def __init__(self, config: ConfigData, model: Model) -> None:
        self._config = config
        self._model = model

    def __getitem__(self, key: str) -> Any:
        return self._config.get(key)

    def _get_secret(self, secret_id: str) -> dict[str, str]:
        secret = self._model.get_secret(id=secret_id)
        return secret.get_content(refresh=True)

    def get_system_secret(self) -> Optional[list[str]]:
        if not (secret_id := self._config.get("initial_system_secret_id")):
            return None

        try:
            content = self._get_secret(secret_id)
        except SecretNotFoundError:
            return None
        except Exception as e:
            raise InvalidHydraConfig from e
        if any(len(s) < 16 for s in content.values()):
            raise InvalidHydraConfig("key must be >16 chars")
        return [secret for _, secret in sorted(content.items(), reverse=True)]

    def get_cookie_secret(self) -> Optional[list[str]]:
        if not (secret_id := self._config.get("initial_cookie_secret_id")):
            return None

        try:
            content = self._get_secret(secret_id)
        except SecretNotFoundError:
            return None
        except Exception as e:
            raise InvalidHydraConfig from e
        if any(len(s) < 16 for s in content.values()):
            raise InvalidHydraConfig("key must be >16 chars")
        return [secret for _, secret in sorted(content.items(), reverse=True)]

    def to_service_configs(self) -> ServiceConfigs:
        config = {
            "dev_mode": self._config["dev"],
            "log_level": self._config["log_level"],
            "access_token_strategy": "jwt" if self._config["jwt_access_tokens"] else "opaque",
        }

        return config

    def to_env_vars(self) -> EnvVars:
        return {
            "DEV": "true" if self._config["dev"] else "false",
        }


class ConfigFile:
    """An abstraction of the workload service configurations."""

    def __init__(self, content: str) -> None:
        self.content = content

    @classmethod
    def from_sources(cls, *service_config_sources: ServiceConfigSource) -> "ConfigFile":
        with open("templates/hydra.yaml.j2", "r") as file:
            template = Template(file.read())

        configs = {
            **{"supported_scopes": DEFAULT_OAUTH_SCOPES},
            **ChainMap(*(source.to_service_configs() for source in service_config_sources)),  # type: ignore
        }
        rendered = template.render(configs)

        return cls(rendered)

    @classmethod
    def from_workload_container(cls, workload_container: Container) -> Self:
        try:
            with workload_container.pull(CONFIG_FILE_NAME, encoding="utf-8") as config_file:
                return cls(config_file.read())
        except PathError:
            return cls("")

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, ConfigFile):
            return NotImplemented

        return self.content == other.content

    def __str__(self) -> str:
        return self.content
