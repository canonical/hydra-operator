# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

from collections import ChainMap
from typing import Any, Mapping, Protocol, TypeAlias

from jinja2 import Template
from ops import ConfigData

from constants import DEFAULT_OAUTH_SCOPES

ServiceConfigs: TypeAlias = Mapping[str, Any]


class ServiceConfigSource(Protocol):
    def to_service_configs(self) -> ServiceConfigs:
        pass


class CharmConfig:
    """A class representing the data source of charm configurations."""

    def __init__(self, config: ConfigData) -> None:
        self._config = config

    def to_service_configs(self) -> ServiceConfigs:
        return {
            "dev_mode": self._config["dev"],
            "log_level": self._config["log_level"],
            "access_token_strategy": "jwt" if self._config["jwt_access_tokens"] else "opaque",
        }


class ConfigFile:
    @classmethod
    def from_sources(cls, *service_config_sources: ServiceConfigSource) -> str:
        with open("templates/hydra.yaml.j2", "r") as file:
            template = Template(file.read())

        configs = {
            **{"supported_scopes": DEFAULT_OAUTH_SCOPES},
            **ChainMap(*(source.to_service_configs() for source in service_config_sources)),  # type: ignore
        }
        rendered = template.render(configs)

        return rendered
