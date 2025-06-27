# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Any, Generator, List

import pytest
from charms.hydra.v0.hydra_token_hook import (
    HydraHookProvider,
    ProviderData,
    ReadyEvent,
    UnavailableEvent,
)
from ops.charm import CharmBase
from ops.framework import EventBase
from ops.testing import Harness

METADATA = """
name: provider-tester
provides:
  hydra-token-hook:
    interface: hydra_token_hook
"""

data = ProviderData(
    url="https://path/to/hook",
    auth_type="api_key",
    auth_config_name="Authorization",
    auth_config_value="token",
    auth_config_in="header",
)


class HydraTokenHookProviderCharm(CharmBase):
    def __init__(self, *args: Any, data: ProviderData = data) -> None:
        super().__init__(*args)
        self.token_hook = HydraHookProvider(self)
        self.events: List = []
        self.data = data

        self.framework.observe(self.token_hook.on.ready, self._on_ready)
        self.framework.observe(self.token_hook.on.unavailable, self._record_event)

    def _on_ready(self, event: EventBase) -> None:
        self.token_hook.update_relations_app_data(self.data)
        self._record_event(event)

    def _record_event(self, event: EventBase) -> None:
        self.events.append(event)


@pytest.fixture()
def harness() -> Generator:
    harness = Harness(HydraTokenHookProviderCharm, meta=METADATA)
    harness.set_leader(True)
    harness.begin()
    yield harness
    harness.cleanup()


def test_provider_info_in_relation_databag(harness: Harness) -> None:
    relation_id = harness.add_relation("hydra-token-hook", "requirer")

    relation_data = harness.get_relation_data(relation_id, harness.model.app.name)

    assert relation_data["url"] == "https://path/to/hook"

    assert isinstance(harness.charm.events[0], ReadyEvent)
    assert relation_data == {
        "url": "https://path/to/hook",
        "auth_config_name": "Authorization",
        "auth_config_value": "token",
        "auth_config_in": "header",
    }


def test_provider_info_in_relation_databag_with_no_auth(harness: Harness) -> None:
    harness.charm.data = ProviderData(url="https://path/to/hook")
    relation_id = harness.add_relation("hydra-token-hook", "requirer")

    relation_data = harness.get_relation_data(relation_id, harness.model.app.name)

    assert isinstance(harness.charm.events[0], ReadyEvent)
    assert relation_data == {"url": "https://path/to/hook"}


def test_unavailable_event_emitted_when_relation_removed(harness: Harness) -> None:
    relation_id = harness.add_relation("hydra-token-hook", "requirer")
    harness.add_relation_unit(relation_id, "requirer/0")
    harness.remove_relation(relation_id)

    assert any(isinstance(e, UnavailableEvent) for e in harness.charm.events)
