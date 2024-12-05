# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
from dataclasses import asdict, dataclass
from typing import Any, KeysView, Type, TypeAlias, Union
from urllib.parse import urlparse

import dacite
from charms.data_platform_libs.v0.data_interfaces import DatabaseRequires
from charms.identity_platform_login_ui_operator.v0.login_ui_endpoints import (
    LoginUIEndpointsRequirer,
)
from charms.tempo_k8s.v2.tracing import TracingEndpointRequirer
from charms.traefik_k8s.v2.ingress import IngressPerAppRequirer
from ops.model import Model
from yarl import URL

from configs import ServiceConfigs
from constants import PEER_INTEGRATION_NAME, POSTGRESQL_DSN_TEMPLATE
from env_vars import EnvVars

logger = logging.getLogger(__name__)

JsonSerializable: TypeAlias = Union[dict[str, Any], list[Any], int, str, float, bool, Type[None]]


class PeerData:
    def __init__(self, model: Model) -> None:
        self._model = model
        self._app = model.app

    def __getitem__(self, key: str) -> JsonSerializable:
        if not (peers := self._model.get_relation(PEER_INTEGRATION_NAME)):
            return {}

        value = peers.data[self._app].get(key)
        return json.loads(value) if value else {}

    def __setitem__(self, key: str, value: Any) -> None:
        if not (peers := self._model.get_relation(PEER_INTEGRATION_NAME)):
            return

        peers.data[self._app][key] = json.dumps(value)

    def pop(self, key: str) -> JsonSerializable:
        if not (peers := self._model.get_relation(PEER_INTEGRATION_NAME)):
            return {}

        data = peers.data[self._app].pop(key, None)
        return json.loads(data) if data else {}

    def keys(self) -> KeysView[str]:
        if not (peers := self._model.get_relation(PEER_INTEGRATION_NAME)):
            return KeysView({})

        return peers.data[self._app].keys()


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    """The data source from the database integration."""

    endpoint: str = ""
    database: str = ""
    username: str = ""
    password: str = ""
    migration_version: str = ""

    @property
    def dsn(self) -> str:
        return POSTGRESQL_DSN_TEMPLATE.substitute(
            username=self.username,
            password=self.password,
            endpoint=self.endpoint,
            database=self.database,
        )

    def to_service_configs(self) -> ServiceConfigs:
        return {
            "dsn": self.dsn,
        }

    @classmethod
    def load(cls, requirer: DatabaseRequires) -> "DatabaseConfig":
        if not (database_integrations := requirer.relations):
            return cls()

        integration_id = database_integrations[0].id
        integration_data: dict[str, str] = requirer.fetch_relation_data()[integration_id]

        return cls(
            endpoint=integration_data.get("endpoints", "").split(",")[0],
            database=requirer.database,
            username=integration_data.get("username", ""),
            password=integration_data.get("password", ""),
            migration_version=f"migration_version_{integration_id}",
        )


@dataclass(frozen=True, slots=True)
class TracingData:
    """The data source from the tracing integration."""

    is_ready: bool = False
    http_endpoint: str = ""

    def to_env_vars(self) -> EnvVars:
        if not self.is_ready:
            return {}

        return {
            "TRACING_ENABLED": True,
            "TRACING_PROVIDER": "otel",
            "TRACING_PROVIDERS_OTLP_SERVER_URL": self.http_endpoint,
            "TRACING_PROVIDERS_OTLP_INSECURE": "true",
            "TRACING_PROVIDERS_OTLP_SAMPLING_SAMPLING_RATIO": "1.0",
        }

    @classmethod
    def load(cls, requirer: TracingEndpointRequirer) -> "TracingData":
        if not (is_ready := requirer.is_ready()):
            return cls()

        http_endpoint = urlparse(requirer.get_endpoint("otlp_http"))
        url, scheme = http_endpoint.geturl(), http_endpoint.scheme

        return cls(
            is_ready=is_ready,
            http_endpoint=url.replace(f"{scheme}://", "", 1),  # type: ignore[str-bytes-safe, arg-type]
        )


@dataclass(frozen=True, slots=True)
class LoginUIEndpointData:
    """The data source from the login-ui integration."""

    consent_url: str = ""
    device_verification_url: str = ""
    oidc_error_url: str = ""
    login_url: str = ""
    post_device_done_url: str = ""

    def to_service_configs(self) -> ServiceConfigs:
        return asdict(self)

    @classmethod
    def load(cls, requirer: LoginUIEndpointsRequirer) -> "LoginUIEndpointData":
        try:
            login_ui_endpoints = requirer.get_login_ui_endpoints()
        except Exception as exc:
            logger.error("Failed to fetch the login ui endpoints: %s", exc)
            return cls()

        return dacite.from_dict(data_class=LoginUIEndpointData, data=login_ui_endpoints)


@dataclass(frozen=True, slots=True)
class PublicIngressData:
    """The data source from the public-ingress integration."""

    url: URL = URL()

    def to_service_configs(self) -> ServiceConfigs:
        return {"public_url": str(self.url)}

    @classmethod
    def load(cls, requirer: IngressPerAppRequirer) -> "PublicIngressData":
        return cls(url=URL(requirer.url)) if requirer.is_ready() else cls()  # type: ignore[arg-type]
