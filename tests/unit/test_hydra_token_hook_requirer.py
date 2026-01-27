# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Any, Optional

import pytest
import yaml
from charms.hydra.v0.hydra_token_hook import (
    AuthIn,
    HydraHookRequirer,
    ProviderData,
    UnavailableEvent,
)
from ops.charm import CharmBase
from ops.testing import Context, Relation
from unit.conftest import create_state

METADATA = """
name: requirer-tester
requires:
  hydra-token-hook:
    interface: hydra_token_hook
"""


class HydraTokenHookRequirerCharm(CharmBase):
    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self._received_data: Optional[ProviderData] = None
        self.token_hook = HydraHookRequirer(self)

    @property
    def received_data(self) -> Optional[ProviderData]:
        return self.token_hook.consume_relation_data(self.model.get_relation("hydra-token-hook"))


@pytest.fixture()
def provider_data() -> ProviderData:
    return ProviderData(
        url="https://path/to/hook",
        auth_config_name="Authorization",
        auth_config_value="token",
        auth_config_in=AuthIn.header,
    )


@pytest.fixture
def context() -> Context:
    return Context(HydraTokenHookRequirerCharm, meta=yaml.safe_load(METADATA))


def test_data_in_relation_bag(context: Context, provider_data: ProviderData) -> None:
    data_dump = provider_data.model_dump(exclude_none=True)
    relation = Relation("hydra-token-hook", remote_app_data=data_dump)
    state = create_state(leader=True, relations=[relation], containers=[])

    with context(context.on.relation_changed(relation), state) as mgr:
        mgr.run()
        assert mgr.charm.received_data == provider_data


def test_data_in_relation_bag_with_no_auth(context: Context) -> None:
    provider_data = ProviderData(url="https://path/to/hook")
    data_dump = provider_data.model_dump(exclude_none=True)

    relation = Relation("hydra-token-hook", remote_app_data=data_dump)
    state = create_state(leader=True, relations=[relation], containers=[])

    with context(context.on.relation_changed(relation), state) as mgr:
        mgr.run()
        assert mgr.charm.received_data == provider_data


def test_unavailable_event_emitted_when_relation_removed(context: Context) -> None:
    relation = Relation("hydra-token-hook")
    state = create_state(leader=True, relations=[relation], containers=[])

    context.run(context.on.relation_broken(relation), state)

    assert any(isinstance(e, UnavailableEvent) for e in context.emitted_events)
