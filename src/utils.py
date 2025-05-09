# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

from functools import wraps
from typing import Any, Callable, Optional, TypeVar

from ops.charm import CharmBase

from constants import (
    DATABASE_INTEGRATION_NAME,
    LOGIN_UI_INTEGRATION_NAME,
    PEER_INTEGRATION_NAME,
    PUBLIC_INGRESS_INTEGRATION_NAME,
    WORKLOAD_CONTAINER,
)

CharmEventHandler = TypeVar("CharmEventHandler", bound=Callable[..., Any])
Condition = Callable[[CharmBase], bool]


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
public_ingress_integration_exists = integration_existence(PUBLIC_INGRESS_INTEGRATION_NAME)
login_ui_integration_exists = integration_existence(LOGIN_UI_INTEGRATION_NAME)


def container_connectivity(charm: CharmBase) -> bool:
    return charm.unit.get_container(WORKLOAD_CONTAINER).can_connect()
