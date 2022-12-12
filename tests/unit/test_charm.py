# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import pytest
import yaml
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.testing import Harness

from charm import HydraCharm

CONTAINER_NAME = "hydra"
DB_USERNAME = "test-username"
DB_PASSWORD = "test-password"
DB_ENDPOINT = "postgresql-k8s-primary.namespace.svc.cluster.local:5432"


@pytest.fixture()
def harness():
    harness = Harness(HydraCharm)
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


def setup_postgres_relation(harness):
    db_relation_id = harness.add_relation("pg-database", "postgresql-k8s")
    harness.add_relation_unit(db_relation_id, "postgresql-k8s/0")
    harness.update_relation_data(
        db_relation_id,
        "postgresql-k8s",
        {
            "data": '{"database": "hydra", "extra-user-roles": "SUPERUSER"}',
            "endpoints": DB_ENDPOINT,
            "password": DB_PASSWORD,
            "username": DB_USERNAME,
        },
    )

    return db_relation_id


def test_not_leader(harness, mocked_kubernetes_service_patcher):
    harness.set_leader(False)
    harness.begin()
    setup_postgres_relation(harness)

    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    assert (
        "status_set",
        "waiting",
        "Waiting for leadership",
        {"is_app": False},
    ) in harness._get_backend_calls()


def test_install_without_relation(harness, mocked_kubernetes_service_patcher):
    harness.begin()

    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)
    assert harness.charm.unit.status == BlockedStatus("Missing required relation with postgresql")


def test_missing_database_details(harness, mocked_kubernetes_service_patcher):
    harness.begin()
    db_relation_id = harness.add_relation("pg-database", "postgresql-k8s")
    harness.add_relation_unit(db_relation_id, "postgresql-k8s/0")

    harness.set_can_connect(CONTAINER_NAME, True)
    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    assert harness.charm.unit.status == MaintenanceStatus("Configuring resources")


def test_relation_data(harness, mocked_kubernetes_service_patcher, mocked_sql_migration):
    db_relation_id = setup_postgres_relation(harness)
    harness.begin_with_initial_hooks()

    relation_data = harness.get_relation_data(db_relation_id, "postgresql-k8s")
    assert relation_data["username"] == "test-username"
    assert relation_data["password"] == "test-password"
    assert relation_data["endpoints"] == "postgresql-k8s-primary.namespace.svc.cluster.local:5432"


def test_relation_departed(harness, mocked_kubernetes_service_patcher, mocked_sql_migration):
    harness.begin()
    db_relation_id = setup_postgres_relation(harness)

    harness.remove_relation_unit(db_relation_id, "postgresql-k8s/0")
    assert harness.charm.unit.status == BlockedStatus("Missing required relation with postgresql")


def test_pebble_container_can_connect(
    harness, mocked_kubernetes_service_patcher, mocked_sql_migration
):
    harness.begin()
    setup_postgres_relation(harness)
    harness.set_can_connect(CONTAINER_NAME, True)

    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    assert isinstance(harness.charm.unit.status, ActiveStatus)
    assert harness.get_container_pebble_plan("hydra")._services is not None


def test_pebble_container_cannot_connect(
    harness, mocked_kubernetes_service_patcher, mocked_sql_migration
):
    harness.begin()
    setup_postgres_relation(harness)
    harness.set_can_connect(CONTAINER_NAME, False)

    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    assert harness.charm.unit.status == WaitingStatus("Waiting to connect to Hydra container")


def test_update_container_config(harness, mocked_kubernetes_service_patcher, mocked_sql_migration):
    harness.begin()
    harness.set_can_connect(CONTAINER_NAME, True)
    setup_postgres_relation(harness)

    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    expected_config = {
        "dsn": f"postgres://{DB_USERNAME}:{DB_PASSWORD}@{DB_ENDPOINT}/hydra",
        "log": {"level": "trace"},
        "secrets": {
            "cookie": ["my-cookie-secret"],
            "system": ["my-system-secret"],
        },
        "serve": {
            "admin": {
                "host": "localhost",
                "port": 4445,
            },
            "public": {
                "host": "localhost",
                "port": 4444,
            },
        },
        "urls": {
            "consent": "http://localhost:3000/consent",
            "login": "http://localhost:3000/login",
            "self": {
                "issuer": "http://localhost:4444/",
                "public": "http://localhost:4444/",
            },
        },
    }

    assert harness.charm._config == yaml.dump(expected_config)
    assert harness.charm.unit.status == ActiveStatus()
