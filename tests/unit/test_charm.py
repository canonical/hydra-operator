# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import pytest
import yaml
from ops.model import BlockedStatus, MaintenanceStatus, WaitingStatus

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


def setup_ingress_relation(harness, type):
    relation_id = harness.add_relation(f"{type}-ingress", f"{type}-traefik")
    harness.add_relation_unit(relation_id, f"{type}-traefik/0")
    harness.update_relation_data(
        relation_id,
        f"{type}-traefik",
        {"url": f"http://{type}:80/{harness.model.name}-hydra"},
    )
    return relation_id


def test_not_leader(harness, mocked_kubernetes_service_patcher):
    harness.begin()
    setup_postgres_relation(harness)
    harness.set_can_connect(CONTAINER_NAME, True)
    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)
    assert harness.charm.unit.status == WaitingStatus("Waiting for leadership")


def test_install_without_relation(harness, mocked_kubernetes_service_patcher):
    harness.set_leader(True)
    harness.begin()

    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)
    assert harness.charm.unit.status == BlockedStatus("Missing required relation with postgresql")


def test_pebble_container_can_connect(
    harness, mocked_kubernetes_service_patcher, mocked_update_container
):
    harness.set_leader(True)
    harness.begin()
    setup_postgres_relation(harness)
    harness.set_can_connect(CONTAINER_NAME, True)

    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    assert isinstance(harness.charm.unit.status, MaintenanceStatus)
    assert harness.get_container_pebble_plan("hydra")._services is not None


def test_pebble_container_cannot_connect(harness, mocked_kubernetes_service_patcher):
    harness.set_leader(True)
    harness.begin()
    setup_postgres_relation(harness)
    harness.set_can_connect(CONTAINER_NAME, False)

    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    assert harness.charm.unit.status == WaitingStatus("Waiting to connect to Hydra container")


def test_missing_relation_data(harness, mocked_kubernetes_service_patcher):
    harness.set_leader(True)
    db_relation_id = harness.add_relation("pg-database", "postgresql-k8s")
    harness.add_relation_unit(db_relation_id, "postgresql-k8s/0")

    harness.begin_with_initial_hooks()
    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    assert harness.charm.unit.status == WaitingStatus("Waiting for database creation")


def test_relation_data(harness, mocked_kubernetes_service_patcher):
    harness.set_leader(True)
    db_relation_id = setup_postgres_relation(harness)
    harness.begin_with_initial_hooks()

    relation_data = harness.get_relation_data(db_relation_id, "postgresql-k8s")
    assert relation_data["username"] == "test-username"
    assert relation_data["password"] == "test-password"
    assert relation_data["endpoints"] == "postgresql-k8s-primary.namespace.svc.cluster.local:5432"


def test_events(harness, mocked_kubernetes_service_patcher, mocked_update_container):
    harness.set_leader(True)
    harness.begin()
    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    mocked_update_container.assert_called_once()

    setup_postgres_relation(harness)
    assert mocked_update_container.call_count == 2


def test_update_container_config(
    harness, mocked_kubernetes_service_patcher, mocked_update_container
):
    harness.set_leader(True)
    harness.begin()
    harness.set_can_connect(CONTAINER_NAME, True)
    setup_postgres_relation(harness)

    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    mocked_update_container.assert_called()
    assert isinstance(harness.charm.unit.status, MaintenanceStatus)

    expected_config = {
        "dsn": f"postgres://{DB_USERNAME}:{DB_PASSWORD}@{DB_ENDPOINT}/postgres",
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


@pytest.mark.parametrize("api_type,port", [("admin", "4445"), ("public", "4444")])
def test_ingress_relation_created(
    harness, mocked_kubernetes_service_patcher, mocked_fqdn, api_type, port
) -> None:
    harness.set_leader(True)
    harness.begin()
    harness.set_can_connect(CONTAINER_NAME, True)

    relation_id = setup_ingress_relation(harness, api_type)
    app_data = harness.get_relation_data(relation_id, harness.charm.app)

    assert app_data == {
        "host": mocked_fqdn.return_value,
        "model": harness.model.name,
        "name": "hydra",
        "port": port,
        "strip-prefix": "true",
    }
