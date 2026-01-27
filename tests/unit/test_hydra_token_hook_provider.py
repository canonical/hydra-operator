# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Any

import pytest
import yaml
from charms.hydra.v0.hydra_token_hook import (
    AuthIn,
    HydraHookProvider,
    ProviderData,
    UnavailableEvent,
)
from ops.charm import CharmBase
from ops.framework import EventBase
from ops.testing import Context, Relation
from unit.conftest import create_state

METADATA = """
name: provider-tester
provides:
  hydra-token-hook:
    interface: hydra_token_hook
"""

provider_data = ProviderData(
    url="https://path/to/hook",
    auth_config_name="Authorization",
    auth_config_value="token",
    auth_config_in=AuthIn.header,
)


class HydraTokenHookProviderCharm(CharmBase):
    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.provider_data = provider_data
        self.token_hook = HydraHookProvider(self)

        self.framework.observe(self.token_hook.on.ready, self._on_ready)

    def _on_ready(self, event: EventBase) -> None:
        self.token_hook.update_relations_app_data(self.provider_data)


class NoAuthHydraTokenHookProviderCharm(HydraTokenHookProviderCharm):
    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.provider_data = ProviderData(url="https://path/to/hook")


@pytest.fixture
def context() -> Context:
    return Context(HydraTokenHookProviderCharm, meta=yaml.safe_load(METADATA))


@pytest.fixture
def context_no_auth() -> Context:
    return Context(NoAuthHydraTokenHookProviderCharm, meta=yaml.safe_load(METADATA))


def test_provider_info_in_relation_databag(context: Context) -> None:
    relation = Relation("hydra-token-hook")
    state = create_state(leader=True, relations=[relation], containers=[])

    with context(context.on.relation_created(relation), state) as mgr:
        state_out = mgr.run()
        assert state_out.get_relation(relation.id).local_app_data["url"] == "https://path/to/hook"
        assert (
            state_out.get_relation(relation.id).local_app_data["auth_config_name"]
            == "Authorization"
        )


def test_provider_info_in_relation_databag_with_no_auth(context_no_auth: Context) -> None:
    relation = Relation("hydra-token-hook")
    state = create_state(leader=True, relations=[relation], containers=[])

    with context_no_auth(context_no_auth.on.relation_created(relation), state) as mgr:
        state_out = mgr.run()
        relation_data = state_out.get_relation(relation.id).local_app_data
        assert relation_data["url"] == "https://path/to/hook"
        assert "auth_config_name" not in relation_data


def test_unavailable_event_emitted_when_relation_removed(context: Context) -> None:
    relation = Relation("hydra-token-hook")
    state = create_state(leader=True, relations=[relation], containers=[])

    with context(context.on.relation_broken(relation), state) as mgr:
        mgr.run()
        assert any(isinstance(e, UnavailableEvent) for e in context.emitted_events)
