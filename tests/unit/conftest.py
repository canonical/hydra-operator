# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import pytest
from ops.testing import Harness

from charm import HydraCharm


@pytest.fixture()
def harness():
    harness = Harness(HydraCharm)
    harness.set_model_name("testing")
    harness.set_leader(True)
    return harness


@pytest.fixture()
def mocked_kubernetes_service_patcher(mocker):
    mocked_service_patcher = mocker.patch("charm.KubernetesServicePatch")
    mocked_service_patcher.return_value = lambda x, y: None
    yield mocked_service_patcher


@pytest.fixture()
def mocked_sql_migration(mocker):
    mocked_sql_migration = mocker.patch("charm.HydraCharm._run_sql_migration")
    yield mocked_sql_migration


@pytest.fixture()
def mocked_fqdn(mocker):
    mocked_fqdn = mocker.patch("socket.getfqdn")
    mocked_fqdn.return_value = "hydra"
    return mocked_fqdn
