# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import pytest
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.testing import Harness

from charm import HydraCharm


@pytest.fixture()
def harness():
    return Harness(HydraCharm)


def test_leadership_events(harness):
    """Test leader-elected event handling."""
    harness.set_leader(False)
    harness.begin_with_initial_hooks()
    assert harness.charm.model.unit.status == WaitingStatus("Waiting for leadership")
    harness.set_leader(True)
    assert harness.charm.model.unit.status != WaitingStatus("Waiting for leadership")
    harness.set_leader(False)
    # Emit another leader_elected event due to https://github.com/canonical/operator/issues/812
    harness._charm.on.leader_elected.emit()
    assert harness.charm.model.unit.status == WaitingStatus("Waiting for leadership")


def test_pebble_container_can_connect(harness):
    harness.set_leader(True)
    harness.begin()

    harness.set_can_connect("hydra", True)
    assert isinstance(harness.charm.unit.status, MaintenanceStatus)
    assert harness.get_container_pebble_plan("hydra")._services is not None

    harness.charm._push_config()
    assert not isinstance(harness.charm.unit.status, BlockedStatus)


def test_install_without_relation(harness):
    harness.set_leader(True)
    harness.begin()

    harness.charm.on.install.emit()
    assert isinstance(harness.charm.unit.status, BlockedStatus)

    assert (
        "status_set",
        "blocked",
        "Missing required relation for postgresql",
        {"is_app": False},
    ) in harness._get_backend_calls()


def test_install_with_relation(harness):
    harness.set_leader(True)
    rel_id = harness.add_relation("pg-database", "app")
    harness.add_relation_unit(rel_id, "app/0")
    harness.update_relation_data(
        rel_id,
        "app",
        {"_supported_versions": "- v1"},
    )
    harness.begin()

    harness.charm.on.install.emit()
    assert isinstance(harness.charm.unit.status, ActiveStatus)


def test_events(harness, mocker):
    harness.set_leader(True)
    harness.begin()
    main = mocker.patch("charm.HydraCharm.main")

    harness.charm.on.install.emit()
    main.assert_called_once()
    main.reset_mock()

    harness.charm.on.config_changed.emit()
    main.assert_called_once()
    main.reset_mock()


def test_config_changed(harness, mocker):
    harness.set_leader(True)
    update_layer = mocker.patch("charm.HydraCharm._update_layer")

    rel_id = harness.add_relation("pg-database", "app")
    harness.add_relation_unit(rel_id, "app/0")
    harness.update_relation_data(
        rel_id,
        "app",
        {"_supported_versions": "- v1"},
    )
    harness.begin()

    harness.update_config({"system-secret": "new-secret"})

    update_layer.assert_called()
