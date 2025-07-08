# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import hashlib
from collections import ChainMap
from typing import Any, Mapping, Protocol, TypeAlias

from jinja2 import Template
from ops import ConfigData

from constants import DEFAULT_OAUTH_SCOPES
from env_vars import EnvVars

ServiceConfigs: TypeAlias = Mapping[str, Any]


class ServiceConfigSource(Protocol):
    """An interface enforcing the contribution to workload service configs."""

    def to_service_configs(self) -> ServiceConfigs:
        pass


class CharmConfig:
    """A class representing the data source of charm configurations."""

    def __init__(self, config: ConfigData) -> None:
        self._config = config

    def __getitem__(self, key: str) -> Any:
        return self._config.get(key)

    def to_service_configs(self) -> ServiceConfigs:
        return {
            "dev_mode": self._config["dev"],
            "log_level": self._config["log_level"],
            "access_token_strategy": "jwt" if self._config["jwt_access_tokens"] else "opaque",
        }

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

    def __hash__(self) -> int:
        # Do not use the builtin `hash` function, the salt changes on every interpreter
        # run making it useless in charms
        return int(hashlib.md5(self.content.encode()).hexdigest(), 16)

    def __str__(self) -> str:
        return self.content
