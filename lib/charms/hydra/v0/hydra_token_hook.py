# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Interface library for configuring the hydra token hook.

The provider side is responsible for providing the configuration that hydra
will use to call this hook.

The requirer side (hydra) takes the configuration provided and updates its
config.
"""

import enum
import logging
from functools import cached_property
from typing import List, Optional

from ops import (
    CharmBase,
    EventBase,
    EventSource,
    Handle,
    Object,
    ObjectEvents,
    Relation,
    RelationBrokenEvent,
    RelationChangedEvent,
    RelationCreatedEvent,
)
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

LIBID = "b2e5e865f0bc43638f1e4a0a63e899a9"
LIBAPI = 0
LIBPATCH = 2

PYDEPS = ["pydantic"]

INTEGRATION_NAME = "hydra-token-hook"
INTERFACE_NAME = "hydra_token_hook"
logger = logging.getLogger(__name__)


class AuthIn(enum.Enum):
    header = "header"
    cookie = "cookie"


class ProviderData(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    url: str
    auth_config_value: Optional[str] = None
    auth_config_name: Optional[str] = Field(
        default_factory=lambda data: "Authorization" if data["auth_config_value"] else None
    )
    auth_config_in: Optional[AuthIn] = Field(
        default_factory=lambda data: AuthIn.header if data["auth_config_value"] else None,
        validate_default=True,
    )

    @cached_property
    def auth_enabled(self) -> bool:
        return all(
            f
            for f in [
                self.auth_config_name,
                self.auth_config_value,
                self.auth_config_in,
            ]
        )


class ReadyEvent(EventBase):
    """An event when the integration is ready."""

    def __init__(
        self,
        handle: Handle,
        relation: Relation,
    ) -> None:
        super().__init__(handle)
        self.relation = relation

    def snapshot(self) -> dict:
        """Save event."""
        return {
            "relation_name": self.relation.name,
            "relation_id": self.relation.id,
        }

    def restore(self, snapshot: dict) -> None:
        """Restore event."""
        relation = self.framework.model.get_relation(
            snapshot["relation_name"], snapshot["relation_id"]
        )
        if relation is None:
            raise ValueError(
                "Unable to restore {}: relation {} (id={}) not found.".format(
                    self, snapshot["relation_name"], snapshot["relation_id"]
                )
            )
        self.relation = relation


class UnavailableEvent(EventBase):
    """An event when the integration is unavailable."""

    def __init__(
        self,
        handle: Handle,
        relation: Relation,
    ) -> None:
        super().__init__(handle)
        self.relation = relation

    def snapshot(self) -> dict:
        """Save event."""
        return {
            "relation_name": self.relation.name,
            "relation_id": self.relation.id,
        }

    def restore(self, snapshot: dict) -> None:
        """Restore event."""
        relation = self.framework.model.get_relation(
            snapshot["relation_name"], snapshot["relation_id"]
        )
        if relation is None:
            raise ValueError(
                "Unable to restore {}: relation {} (id={}) not found.".format(
                    self, snapshot["relation_name"], snapshot["relation_id"]
                )
            )
        self.relation = relation


class RelationEvents(ObjectEvents):
    ready = EventSource(ReadyEvent)
    unavailable = EventSource(UnavailableEvent)


class HydraHookProvider(Object):
    """Provider side of the hydra-token-hook relation."""

    on = RelationEvents()

    def __init__(self, charm: CharmBase, relation_name: str = INTEGRATION_NAME):
        super().__init__(charm, relation_name)

        self._charm = charm
        self._relation_name = relation_name

        events = self._charm.on[relation_name]
        self.framework.observe(events.relation_created, self._on_relation_created)
        self.framework.observe(events.relation_broken, self._on_relation_broken)

    def _on_relation_created(self, event: RelationCreatedEvent) -> None:
        self.on.ready.emit(event.relation)

    def _on_relation_broken(self, event: RelationBrokenEvent) -> None:
        """Handle the event emitted when the integration is broken."""
        self.on.unavailable.emit(event.relation)

    def update_relations_app_data(
        self,
        data: ProviderData,
    ) -> None:
        """Update the integration data."""
        if not self._charm.unit.is_leader():
            return None

        if not (relations := self._charm.model.relations.get(self._relation_name)):
            return None

        for relation in relations:
            relation.data[self._charm.app].update(data.model_dump(exclude_none=True))


class HydraHookRequirer(Object):
    """Requirer side of the hydra-token-hook relation."""

    on = RelationEvents()

    def __init__(self, charm: CharmBase, relation_name: str = INTEGRATION_NAME):
        super().__init__(charm, relation_name)

        self._charm = charm
        self._relation_name = relation_name

        events = self._charm.on[relation_name]
        self.framework.observe(events.relation_changed, self._on_relation_changed)
        self.framework.observe(events.relation_broken, self._on_relation_broken)

    def _on_relation_changed(self, event: RelationChangedEvent) -> None:
        provider_app = event.relation.app

        if not event.relation.data.get(provider_app):
            return

        self.on.ready.emit(event.relation)

    def _on_relation_broken(self, event: RelationBrokenEvent) -> None:
        """Handle the event emitted when the integration is broken."""
        self.on.unavailable.emit(event.relation)

    def consume_relation_data(
        self,
        /,
        relation: Optional[Relation] = None,
        relation_id: Optional[int] = None,
    ) -> Optional[ProviderData]:
        """An API for the requirer charm to consume the related information in the application databag."""
        if not relation:
            relation = self._charm.model.get_relation(self._relation_name, relation_id)

        if not relation:
            return None

        provider_data = dict(relation.data.get(relation.app))
        return ProviderData(**provider_data) if provider_data else None

    @property
    def relations(self) -> List[Relation]:
        """The list of Relation instances associated with this relation_name."""
        return [
            relation
            for relation in self._charm.model.relations[self._relation_name]
            if relation.active
        ]

    def _ready(self, relation: Relation) -> bool:
        if not relation.app:
            return False

        return "url" in relation.data[relation.app]

    def ready(self, relation_id: Optional[int] = None) -> bool:
        """Check if the relation data is ready."""
        if relation_id is None:
            return (
                all(self._ready(relation) for relation in self.relations)
                if self.relations
                else False
            )

        relation = next(
            (relation for relation in self.relations if relation.id == relation_id), None
        )
        return self._ready(relation) if relation else False
