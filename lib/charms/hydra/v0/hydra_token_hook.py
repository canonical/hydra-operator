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
from typing import Annotated, Any, List, Optional, TypeVar, Union, get_args

from ops import (
    CharmBase,
    EventSource,
    Object,
    ObjectEvents,
    Relation,
    RelationBrokenEvent,
    RelationChangedEvent,
    RelationCreatedEvent,
    RelationEvent,
)
from pydantic import BaseModel as _BaseModel
from pydantic import (
    BeforeValidator,
    Field,
    PlainSerializer,
    ValidationInfo,
)
from pydantic_core import from_json

LIBID = "b2e5e865f0bc43638f1e4a0a63e899a9"
LIBAPI = 0
LIBPATCH = 1

PYDEPS = ["pydantic"]

INTEGRATION_NAME = "hydra-token-hook"
INTERFACE_NAME = "hydra_token_hook"
logger = logging.getLogger(__name__)


class BaseModel(_BaseModel):
    def __init__(self, **data: Any) -> None:
        # We override the init function to add a reference to self in the context
        # so that "deserialize_model" can use it.
        self.__pydantic_validator__.validate_python(
            data,
            self_instance=self,
            context={"self": self},
        )


def deserialize_model(v: Union[BaseModel, str], info: ValidationInfo) -> BaseModel:
    if isinstance(v, BaseModel):
        return v

    return info.context["self"].model_fields[info.field_name].annotation(**from_json(v))


def deserialize_optional_model(
    v: Union[BaseModel, str], info: ValidationInfo
) -> Optional[BaseModel]:
    if v == "":
        return None

    if isinstance(v, BaseModel):
        return v

    t = info.context["self"].model_fields[info.field_name].annotation
    for annotation in get_args(t):
        if annotation is not type(None):
            return annotation(**from_json(v))


SerializableModel = Annotated[
    TypeVar("BaseModelType", bound=BaseModel),
    PlainSerializer(lambda v: v.model_dump_json(), return_type=str),
    BeforeValidator(deserialize_model),
]


OptionalSerializableModel = Annotated[
    Optional[TypeVar("BaseModelType", bound=BaseModel)],
    PlainSerializer(lambda v: v.model_dump_json() if v else "", return_type=str),
    BeforeValidator(deserialize_optional_model),
]


class AuthType(enum.Enum):
    api_key = "api_key"
    cookie = "cookie"


class _AuthConfig(BaseModel):
    name: str = "Authorization"
    value: str
    in_: str = Field(default="header", alias="in")


class AuthConfig(BaseModel):
    type: AuthType = AuthType.api_key
    config: SerializableModel[_AuthConfig]


class ProviderData(BaseModel):
    url: str
    auth: OptionalSerializableModel[AuthConfig] = None


class ReadyEvent(RelationEvent):
    """An event when the integration is ready."""


class UnavailableEvent(RelationEvent):
    """An event when the integration is unavailable."""


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

        relation = next((relation for relation in self.relations if relation.id == relation_id), None)
        return self._ready(relation) if relation else False
