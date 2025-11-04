# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Optional, TypeVar

from ops.charm import CharmBase

from constants import (
    DATABASE_INTEGRATION_NAME,
    LOGIN_UI_INTEGRATION_NAME,
    PEER_INTEGRATION_NAME,
    PUBLIC_ROUTE_INTEGRATION_NAME,
    WORKLOAD_CONTAINER,
)
from integrations import LoginUIEndpointData, PublicRouteData

if TYPE_CHECKING:
    from charm import HydraCharm

CharmEventHandler = TypeVar("CharmEventHandler", bound=Callable[..., Any])
CharmType = TypeVar("CharmType", bound=CharmBase)
Condition = Callable[[CharmType], bool]


def leader_unit(func: CharmEventHandler) -> CharmEventHandler:
    """A decorator, applied to any event hook handler, to validate juju unit leadership."""

    @wraps(func)
    def wrapper(charm: CharmBase, *args: Any, **kwargs: Any) -> Optional[Any]:
        if not charm.unit.is_leader():
            return None

        return func(charm, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


def integration_existence(integration_name: str) -> Condition:
    """A factory of integration existence condition."""

    def wrapped(charm: CharmBase) -> bool:
        return bool(charm.model.relations[integration_name])

    return wrapped


peer_integration_exists = integration_existence(PEER_INTEGRATION_NAME)
database_integration_exists = integration_existence(DATABASE_INTEGRATION_NAME)
public_route_integration_exists = integration_existence(PUBLIC_ROUTE_INTEGRATION_NAME)
login_ui_integration_exists = integration_existence(LOGIN_UI_INTEGRATION_NAME)


def public_route_is_ready(charm: "HydraCharm") -> bool:
    return charm.public_route.is_ready()


def login_ui_is_ready(charm: "HydraCharm") -> bool:
    return LoginUIEndpointData.load(charm.login_ui_requirer).is_ready()


def migration_is_ready(charm: "HydraCharm") -> bool:
    return not charm.migration_needed


def secrets_is_ready(charm: "HydraCharm") -> bool:
    return charm.hydra_secrets.is_ready


def public_route_is_secure(charm: "HydraCharm") -> bool:
    return charm.dev_mode or PublicRouteData.load(charm.public_route).secured


def database_resource_is_created(charm: "HydraCharm") -> bool:
    return charm.database_requirer.is_resource_created()


def container_connectivity(charm: CharmBase) -> bool:
    return charm.unit.get_container(WORKLOAD_CONTAINER).can_connect()


# Condition failure causes early return without doing anything
NOOP_CONDITIONS: tuple[Condition, ...] = (
    peer_integration_exists,
    database_integration_exists,
    public_route_integration_exists,
    login_ui_integration_exists,
    public_route_is_ready,
    login_ui_is_ready,
    migration_is_ready,
    secrets_is_ready,
    public_route_is_secure,
    database_resource_is_created,
)

# Condition failure causes early return with corresponding event deferred
EVENT_DEFER_CONDITIONS: tuple[Condition, ...] = (container_connectivity,)
