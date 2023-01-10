# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import yaml
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus

CONTAINER_NAME = "hydra"
DB_USERNAME = "test-username"
DB_PASSWORD = "test-password"
DB_ENDPOINT = "postgresql-k8s-primary.namespace.svc.cluster.local:5432"


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
        "Unit waiting for leadership to run the migration",
        {"is_app": False},
    ) in harness._get_backend_calls()


def test_install_without_relation(harness, mocked_kubernetes_service_patcher):
    harness.begin()

    harness.set_can_connect(CONTAINER_NAME, True)
    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    assert harness.charm.unit.status == BlockedStatus("Missing required relation with postgresql")


def test_install_without_database(harness, mocked_kubernetes_service_patcher):
    harness.begin()

    db_relation_id = harness.add_relation("pg-database", "postgresql-k8s")
    harness.add_relation_unit(db_relation_id, "postgresql-k8s/0")

    harness.set_can_connect(CONTAINER_NAME, True)
    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    assert harness.charm.unit.status == WaitingStatus("Waiting for database creation")


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
    service = harness.model.unit.get_container(CONTAINER_NAME).get_service("hydra")
    assert service.is_running()


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
        "dsn": f"postgres://{DB_USERNAME}:{DB_PASSWORD}@{DB_ENDPOINT}/testing_hydra",
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
