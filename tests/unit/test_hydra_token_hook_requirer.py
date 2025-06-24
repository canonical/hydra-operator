# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from typing import Any, Dict, Generator, List

import pytest
from charms.hydra.v0.hydra_token_hook import (
    AuthConfig,
    HydraHookRequirer,
    ProviderData,
    ReadyEvent,
    UnavailableEvent,
    _AuthConfig,
)
from ops.charm import CharmBase
from ops.framework import EventBase
from ops.testing import Harness

METADATA = """
name: requirer-tester
requires:
  hydra-token-hook:
    interface: hydra_token_hook
"""


class HydraTokenHookRequirerCharm(CharmBase):
    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.token_hook = HydraHookRequirer(self)
        self.events: List = []

        self.framework.observe(self.token_hook.on.ready, self._record_event)
        self.framework.observe(self.token_hook.on.unavailable, self._record_event)

    def _record_event(self, event: EventBase) -> None:
        self.events.append(event)


@pytest.fixture()
def provider_data() -> ProviderData:
    return ProviderData(
        url="https://path/to/hook",
        auth=AuthConfig(
            type="api_key",
            config=_AuthConfig(
                name="Authorization",
                value="token",
                in_="header",
            ),
        ),
    )


@pytest.fixture()
def harness() -> Generator:
    harness = Harness(HydraTokenHookRequirerCharm, meta=METADATA)
    harness.set_leader(True)
    harness.begin()
    yield harness
    harness.cleanup()


def dict_to_relation_data(dic: Dict) -> Dict:
    return {k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in dic.items()}


def test_data_in_relation_bag(harness: Harness, provider_data: ProviderData) -> None:
    relation_id = harness.add_relation("hydra-token-hook", "provider")
    harness.add_relation_unit(relation_id, "provider/0")
    harness.update_relation_data(
        relation_id,
        "provider",
        provider_data.model_dump(exclude_none=True),
    )

    relation_data = harness.charm.token_hook.consume_relation_data(relation_id)

    assert isinstance(harness.charm.events[0], ReadyEvent)
    assert relation_data == provider_data


def test_data_in_relation_bag_with_no_auth(harness: Harness, provider_data: ProviderData) -> None:
    provider_data.auth = None

    relation_id = harness.add_relation("hydra-token-hook", "provider")
    harness.add_relation_unit(relation_id, "provider/0")
    harness.update_relation_data(
        relation_id,
        "provider",
        provider_data.model_dump(exclude_none=True),
    )

    relation_data = harness.charm.token_hook.consume_relation_data(relation_id)

    assert isinstance(harness.charm.events[0], ReadyEvent)
    assert relation_data == provider_data


def test_unavailable_event_emitted_when_relation_removed(harness: Harness) -> None:
    relation_id = harness.add_relation("hydra-token-hook", "provider")
    harness.add_relation_unit(relation_id, "provider/0")
    harness.remove_relation(relation_id)

    assert any(isinstance(e, UnavailableEvent) for e in harness.charm.events)
