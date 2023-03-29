#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Interface library for adding relation between Ory Hydra and Identity Platform Login UI.
This library provides a Python API for handling data exchange between Hydra and Identity Platform Login UI to establish a relation.
## Getting Started
To get started using the library, you need to fetch the library using `charmcraft`.
```shell
cd some-charm
charmcraft fetch-lib charms.identity_platform_login_ui.v0.hydra_login_ui
```
To use the library from the requirer side:
In the `metadata.yaml` of the charm, add the following:
```yaml
requires:
  ui-endpoint-info:
    interface: hydra_login_ui
    limit: 1
```
Then, to initialise the library:
```python
from charms.hydra.v0.hydra_endpoints import (
    HydraLoginUIRelationError,
    HydraLoginUIRequirer,
)
Class SomeCharm(CharmBase):
    def __init__(self, *args):
        self.hydra_login_ui_relation = HydraLoginUIRequirer(self)
        self.framework.observe(self.on.some_event_emitted, self.some_event_function)
    def some_event_function():
        # fetch the relation info
        try:
            login_ui_endpoint = self.hydra_login_ui_relation.get_identity_platform_login_ui_endpoints()
            self.hydra_login_ui_relation.send_hydra_endpoint(hydra_endpoint)
        except HydraLoginUIRelationError as error:
            ...
```
"""

import logging

from ops.charm import CharmBase, RelationCreatedEvent
from ops.framework import EventBase, EventSource, Object, ObjectEvents
from ops.model import Application

# The unique Charmhub library identifier, never change it
# This library is not yet registered to charmhub
LIBID = "placeholder_id"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 0

RELATION_NAME = "ui-endpoint-info"
INTERFACE_NAME = "hydra_login_ui"
logger = logging.getLogger(__name__)


class HydraLoginUIRelationReadyEvent(EventBase):
    """Event to notify the charm that the relation is ready."""


class HydraLoginUIProviderEvents(ObjectEvents):
    """Event descriptor for events raised by `HydraLoginUIProvider`."""

    ready = EventSource(HydraLoginUIRelationReadyEvent)


class HydraLoginUIRequirerEvents(ObjectEvents):
    """Event descriptor for events raised by `HydraLoginUIProvider`."""

    ready = EventSource(HydraLoginUIRelationReadyEvent)


class HydraLoginUIProvider(Object):
    """Provider side of the ui-endpoint-info relation."""

    on = HydraLoginUIProviderEvents()

    def __init__(self, charm: CharmBase, relation_name: str = RELATION_NAME):
        super().__init__(charm, relation_name)

        self._charm = charm
        self._relation_name = relation_name

        events = self._charm.on[self._relation_name]
        self.framework.observe(
            events.relation_created, self._on_provider_relation_created
        )

    def _on_provider_relation_created(self, event: RelationCreatedEvent):
        self.on.ready.emit()

    def send_identity_platform_login_ui_endpoint(
        self, charm: CharmBase, login_ui_endpoint: str
    ) -> None:
        """Updates relation with identity platform login ui endpoints info."""
        if not self._charm.unit.is_leader():
            return

        relations = self.model.relations[RELATION_NAME]
        for relation in relations:
            relation.data[charm].update(
                {
                    "login_ui_endpoint": login_ui_endpoint,
                }
            )

    def get_hydra_endpoint(self) -> dict:
        """Get hydra endpoint."""
        if not self.model.unit.is_leader():
            return
        endpoint = self.model.relations[self._relation_name]
        if len(endpoint) == 0:
            raise HydraLoginUIRelationMissingError()

        remote_app = [
            app
            for app in endpoint[0].data.keys()
            if isinstance(app, Application) and not app._is_our_app
        ][0]

        data = endpoint[0].data[remote_app]

        if "hydra_endpoint" not in data:
            raise HydraLoginUIRelationDataMissingError(
                f"Missing hydra endpoint in {RELATION_NAME} relation data"
            )

        return {
            "hydra_endpoint": data["hydra_endpoint"],
        }


class HydraLoginUIRelationError(Exception):
    """Base class for the relation exceptions."""

    pass


class HydraLoginUIRelationMissingError(HydraLoginUIRelationError):
    """Raised when the relation is missing."""

    def __init__(self):
        self.message = f"Missing {RELATION_NAME} relation with identity-platform-login-ui"
        super().__init__(self.message)


class HydraLoginUIRelationDataMissingError(HydraLoginUIRelationError):
    """Raised when information is missing from the relation."""

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


class HydraLoginUIRequirer(Object):
    """Requirer side of the relation."""

    on = HydraLoginUIRequirerEvents()

    def __init__(self, charm: CharmBase, relation_name: str = RELATION_NAME):
        super().__init__(charm, relation_name)

        self._charm = charm
        self._relation_name = relation_name

        events = self._charm.on[self._relation_name]
        self.framework.observe(
            events.relation_created, self._on_requirer_relation_created
        )

    def _on_requirer_relation_created(self, event: RelationCreatedEvent):
        self.on.ready.emit()

    def send_hydra_endpoint(
        self, charm: CharmBase, hydra_endpoint: str
    ) -> None:
        """Updates relation with hydra endpoints info."""
        if not self._charm.unit.is_leader():
            return

        relations = self.model.relations[RELATION_NAME]
        for relation in relations:
            relation.data[charm].update(
                {
                    "hydra_endpoint": hydra_endpoint,
                }
            )

    def get_identity_platform_login_ui_endpoint(self) -> dict:
        """Get the identity-platform-login-ui endpoint."""
        if not self.model.unit.is_leader():
            return
        endpoint = self.model.relations[self._relation_name]
        if len(endpoint) == 0:
            raise HydraLoginUIRelationMissingError()

        remote_app = [
            app
            for app in endpoint[0].data.keys()
            if isinstance(app, Application) and not app._is_our_app
        ][0]

        data = endpoint[0].data[remote_app]

        if "login_ui_endpoint" not in data:
            raise HydraLoginUIRelationDataMissingError(
                f"Missing identity_login_ui endpoint in {RELATION_NAME} relation data"
            )

        return {
            "login_ui_endpoint": data["login_ui_endpoint"],
        }
