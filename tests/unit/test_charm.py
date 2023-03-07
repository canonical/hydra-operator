# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging

import pytest
import yaml
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.pebble import Error, ExecError

from tests.unit.test_oauth_requirer import CLIENT_CONFIG

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
        {"ingress": json.dumps({"url": f"http://{type}:80/{harness.model.name}-hydra"})},
    )
    return relation_id


def setup_oauth_relation(harness):
    app_name = "requirer"
    relation_id = harness.add_relation("oauth", app_name)
    harness.add_relation_unit(relation_id, "requirer/0")
    return relation_id, app_name


def test_not_leader(harness):
    harness.set_leader(False)
    setup_postgres_relation(harness)

    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    assert (
        "status_set",
        "waiting",
        "Unit waiting for leadership to run the migration",
        {"is_app": False},
    ) in harness._get_backend_calls()


def test_install_without_relation(harness):
    harness.set_can_connect(CONTAINER_NAME, True)
    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    assert harness.charm.unit.status == BlockedStatus("Missing required relation with postgresql")


def test_install_without_database(harness):
    db_relation_id = harness.add_relation("pg-database", "postgresql-k8s")
    harness.add_relation_unit(db_relation_id, "postgresql-k8s/0")

    harness.set_can_connect(CONTAINER_NAME, True)
    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    assert harness.charm.unit.status == WaitingStatus("Waiting for database creation")


def test_relation_data(harness, mocked_sql_migration):
    db_relation_id = setup_postgres_relation(harness)

    relation_data = harness.get_relation_data(db_relation_id, "postgresql-k8s")
    assert relation_data["username"] == "test-username"
    assert relation_data["password"] == "test-password"
    assert relation_data["endpoints"] == "postgresql-k8s-primary.namespace.svc.cluster.local:5432"


def test_relation_departed(harness, mocked_sql_migration):
    db_relation_id = setup_postgres_relation(harness)

    harness.remove_relation_unit(db_relation_id, "postgresql-k8s/0")
    assert harness.charm.unit.status == BlockedStatus("Missing required relation with postgresql")


def test_pebble_container_can_connect(harness, mocked_sql_migration):
    setup_postgres_relation(harness)
    harness.set_can_connect(CONTAINER_NAME, True)

    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    assert isinstance(harness.charm.unit.status, ActiveStatus)
    service = harness.model.unit.get_container(CONTAINER_NAME).get_service("hydra")
    assert service.is_running()


def test_pebble_container_cannot_connect(harness, mocked_sql_migration):
    setup_postgres_relation(harness)
    harness.set_can_connect(CONTAINER_NAME, False)

    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    assert harness.charm.unit.status == WaitingStatus("Waiting to connect to Hydra container")


def test_update_container_config(harness, mocked_sql_migration):
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
                "cors": {
                    "allowed_origins": ["*"],
                    "enabled": True,
                },
            },
            "public": {
                "cors": {
                    "allowed_origins": ["*"],
                    "enabled": True,
                },
            },
        },
        "urls": {
            "consent": "http://127.0.0.1:4455/consent",
            "error": "http://127.0.0.1:4455/oidc_error",
            "login": "http://127.0.0.1:4455/login",
            "self": {
                "issuer": "http://127.0.0.1:4444/",
                "public": "http://127.0.0.1:4444/",
            },
        },
    }

    assert yaml.safe_load(harness.charm._render_conf_file()) == expected_config


def test_on_config_changed_without_service(harness) -> None:
    setup_postgres_relation(harness)
    harness.update_config({"login_ui_url": "http://some-url"})

    assert harness.charm.unit.status == WaitingStatus("Waiting to connect to Hydra container")


def test_on_config_changed_without_database(harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)
    harness.update_config({"login_ui_url": "http://some-url"})

    assert harness.charm.unit.status == BlockedStatus("Missing required relation with postgresql")


def test_config_updated_on_config_changed(harness, mocked_sql_migration) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)
    setup_postgres_relation(harness)

    harness.update_config({"login_ui_url": "http://some-url"})

    expected_config = {
        "dsn": f"postgres://{DB_USERNAME}:{DB_PASSWORD}@{DB_ENDPOINT}/testing_hydra",
        "log": {"level": "trace"},
        "secrets": {
            "cookie": ["my-cookie-secret"],
            "system": ["my-system-secret"],
        },
        "serve": {
            "admin": {
                "cors": {
                    "allowed_origins": ["*"],
                    "enabled": True,
                },
            },
            "public": {
                "cors": {
                    "allowed_origins": ["*"],
                    "enabled": True,
                },
            },
        },
        "urls": {
            "consent": "http://some-url/consent",
            "error": "http://some-url/oidc_error",
            "login": "http://some-url/login",
            "self": {
                "issuer": "http://127.0.0.1:4444/",
                "public": "http://127.0.0.1:4444/",
            },
        },
        "webfinger": {"oidc_discovery": {"supported_scope": "openid profile email " "phone"}},
    }

    assert yaml.safe_load(harness.charm._render_conf_file()) == expected_config


@pytest.mark.parametrize("api_type,port", [("admin", "4445"), ("public", "4444")])
def test_ingress_relation_created(harness, mocked_fqdn, api_type, port) -> None:
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


def test_config_updated_on_ingress_relation_joined(harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)

    setup_postgres_relation(harness)
    setup_ingress_relation(harness, "public")

    expected_config = {
        "dsn": f"postgres://{DB_USERNAME}:{DB_PASSWORD}@{DB_ENDPOINT}/testing_hydra",
        "log": {"level": "trace"},
        "secrets": {
            "cookie": ["my-cookie-secret"],
            "system": ["my-system-secret"],
        },
        "serve": {
            "admin": {
                "cors": {
                    "allowed_origins": ["*"],
                    "enabled": True,
                },
            },
            "public": {
                "cors": {
                    "allowed_origins": ["*"],
                    "enabled": True,
                },
            },
        },
        "urls": {
            "consent": "http://127.0.0.1:4455/consent",
            "error": "http://127.0.0.1:4455/oidc_error",
            "login": "http://127.0.0.1:4455/login",
            "self": {
                "issuer": "http://public:80/testing-hydra",
                "public": "http://public:80/testing-hydra",
            },
        },
    }

    assert yaml.safe_load(harness.charm._render_conf_file()) == expected_config


def test_hydra_config_on_pebble_ready_without_ingress_relation_data(harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)

    # set relation without data
    relation_id = harness.add_relation("public-ingress", "public-traefik")
    harness.add_relation_unit(relation_id, "public-traefik/0")

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
                "cors": {
                    "allowed_origins": ["*"],
                    "enabled": True,
                },
            },
            "public": {
                "cors": {
                    "allowed_origins": ["*"],
                    "enabled": True,
                },
            },
        },
        "urls": {
            "consent": "http://127.0.0.1:4455/consent",
            "error": "http://127.0.0.1:4455/oidc_error",
            "login": "http://127.0.0.1:4455/login",
            "self": {
                "issuer": "http://127.0.0.1:4444/",
                "public": "http://127.0.0.1:4444/",
            },
        },
    }

    container = harness.model.unit.get_container(CONTAINER_NAME)
    container_config = container.pull(path="/etc/config/hydra.yaml", encoding="utf-8")
    assert yaml.load(container_config.read(), yaml.Loader) == expected_config


def test_hydra_endpoint_info_relation_data_without_ingress_relation_data(harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)

    # set relations without data
    public_ingress_relation_id = harness.add_relation("public-ingress", "public-traefik")
    harness.add_relation_unit(public_ingress_relation_id, "public-traefik/0")
    admin_ingress_relation_id = harness.add_relation("admin-ingress", "admin-traefik")
    harness.add_relation_unit(admin_ingress_relation_id, "admin-traefik/0")

    endpoint_info_relation_id = harness.add_relation("endpoint-info", "kratos")
    harness.add_relation_unit(endpoint_info_relation_id, "kratos/0")

    expected_data = {
        "admin_endpoint": "hydra.testing.svc.cluster.local:4445",
        "public_endpoint": "hydra.testing.svc.cluster.local:4444",
    }

    assert harness.get_relation_data(endpoint_info_relation_id, "hydra") == expected_data


def test_hydra_endpoint_info_relation_data_with_ingress_relation_data(harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)

    setup_ingress_relation(harness, "public")
    setup_ingress_relation(harness, "admin")

    endpoint_info_relation_id = harness.add_relation("endpoint-info", "kratos")
    harness.add_relation_unit(endpoint_info_relation_id, "kratos/0")

    expected_data = {
        "admin_endpoint": "http://admin:80/testing-hydra",
        "public_endpoint": "http://public:80/testing-hydra",
    }

    assert harness.get_relation_data(endpoint_info_relation_id, "hydra") == expected_data


def test_provider_info_in_databag_when_ingress_then_oauth_relation(harness):
    harness.set_can_connect(CONTAINER_NAME, True)

    setup_ingress_relation(harness, "public")
    setup_ingress_relation(harness, "admin")

    harness.begin()
    relation_id, _ = setup_oauth_relation(harness)

    app_data = harness.get_relation_data(relation_id, harness.charm.app)

    assert app_data == {
        "authorization_endpoint": "http://public:80/testing-hydra/oauth2/auth",
        "introspection_endpoint": "http://admin:80/testing-hydra/admin/oauth2/introspect",
        "issuer_url": "http://public:80/testing-hydra",
        "jwks_endpoint": "http://public:80/testing-hydra/.well-known/jwks.json",
        "scope": "openid profile email phone",
        "token_endpoint": "http://public:80/testing-hydra/oauth2/token",
        "userinfo_endpoint": "http://public:80/testing-hydra/userinfo",
    }


def test_provider_info_in_databag_when_oauth_relation_then_ingress(harness):
    harness.begin()
    harness.set_can_connect(CONTAINER_NAME, True)

    relation_id, _ = setup_oauth_relation(harness)
    setup_ingress_relation(harness, "public")
    setup_ingress_relation(harness, "admin")

    app_data = harness.get_relation_data(relation_id, harness.charm.app)

    assert app_data == {
        "authorization_endpoint": "http://public:80/testing-hydra/oauth2/auth",
        "introspection_endpoint": "http://admin:80/testing-hydra/admin/oauth2/introspect",
        "issuer_url": "http://public:80/testing-hydra",
        "jwks_endpoint": "http://public:80/testing-hydra/.well-known/jwks.json",
        "scope": "openid profile email phone",
        "token_endpoint": "http://public:80/testing-hydra/oauth2/token",
        "userinfo_endpoint": "http://public:80/testing-hydra/userinfo",
    }


def test_client_created_event(harness, mocked_create_client):
    harness.begin_with_initial_hooks()
    harness.set_can_connect(CONTAINER_NAME, True)

    relation_id, _ = setup_oauth_relation(harness)
    harness.charm.oauth.on.client_created.emit(relation_id=relation_id, **CLIENT_CONFIG)
    app_data = harness.get_relation_data(relation_id, harness.charm.app)

    assert mocked_create_client.called
    assert "client_id" in app_data
    assert "client_secret_id" in app_data


def test_client_created_event_when_cannot_connect(harness, mocked_create_client):
    harness.begin_with_initial_hooks()
    harness.set_can_connect(CONTAINER_NAME, False)

    relation_id, _ = setup_oauth_relation(harness)
    harness.charm.oauth.on.client_created.emit(relation_id=relation_id, **CLIENT_CONFIG)

    assert not mocked_create_client.called


def test_client_created_event_when_no_service(harness, mocked_create_client):
    harness.begin()
    harness.set_can_connect(CONTAINER_NAME, True)

    relation_id, _ = setup_oauth_relation(harness)
    harness.charm.oauth.on.client_created.emit(relation_id=relation_id, **CLIENT_CONFIG)

    assert not mocked_create_client.called


def test_client_created_event_when_exec_error(harness, mocked_create_client, caplog):
    caplog.set_level(logging.ERROR)
    harness.begin_with_initial_hooks()
    harness.set_can_connect(CONTAINER_NAME, True)
    err = ExecError(command="hydra client client 1234", exit_code=1, stdout="Out", stderr="Error")
    mocked_create_client.side_effect = err

    relation_id, _ = setup_oauth_relation(harness)
    harness.charm.oauth.on.client_created.emit(relation_id=relation_id, **CLIENT_CONFIG)

    assert len(caplog.record_tuples) == 1
    assert caplog.record_tuples[0][2] == f"Exited with code: {err.exit_code}. Stderr: {err.stderr}"


def test_client_created_event_when_error(harness, mocked_create_client, caplog):
    caplog.set_level(logging.ERROR)
    harness.begin_with_initial_hooks()
    harness.set_can_connect(CONTAINER_NAME, True)
    err = Error("Some error")
    mocked_create_client.side_effect = err

    relation_id, _ = setup_oauth_relation(harness)
    harness.charm.oauth.on.client_created.emit(relation_id=relation_id, **CLIENT_CONFIG)

    assert len(caplog.record_tuples) == 1
    assert (
        caplog.record_tuples[0][2] == f"Something went wrong when trying to run the command: {err}"
    )


def test_client_config_changed_event(harness, mocked_hydra_cli):
    harness.begin_with_initial_hooks()
    harness.set_can_connect(CONTAINER_NAME, True)

    relation_id, _ = setup_oauth_relation(harness)
    harness.charm.oauth.on.client_config_changed.emit(
        relation_id=relation_id, client_id="client_id", **CLIENT_CONFIG
    )

    assert mocked_hydra_cli.called


def test_client_config_changed_event_when_cannot_connect(
    harness, mocked_kubernetes_service_patcher, mocked_hydra_cli
):
    harness.begin_with_initial_hooks()
    harness.set_can_connect(CONTAINER_NAME, False)

    relation_id, _ = setup_oauth_relation(harness)
    harness.charm.oauth.on.client_config_changed.emit(
        relation_id=relation_id, client_id="client_id", **CLIENT_CONFIG
    )

    assert not mocked_hydra_cli.called


def test_client_config_changed_event_when_no_service(
    harness, mocked_kubernetes_service_patcher, mocked_hydra_cli
):
    harness.begin()
    harness.set_can_connect(CONTAINER_NAME, True)

    relation_id, _ = setup_oauth_relation(harness)
    harness.charm.oauth.on.client_config_changed.emit(
        relation_id=relation_id, client_id="client_id", **CLIENT_CONFIG
    )

    assert not mocked_hydra_cli.called


def test_client_config_changed_event_when_exec_error(
    harness, mocked_kubernetes_service_patcher, mocked_hydra_cli, caplog
):
    caplog.set_level(logging.ERROR)
    harness.begin_with_initial_hooks()
    harness.set_can_connect(CONTAINER_NAME, True)
    err = ExecError(command="hydra client client 1234", exit_code=1, stdout="Out", stderr="Error")
    mocked_hydra_cli.side_effect = err

    relation_id, _ = setup_oauth_relation(harness)
    harness.charm.oauth.on.client_config_changed.emit(
        relation_id=relation_id, client_id="client_id", **CLIENT_CONFIG
    )

    assert len(caplog.record_tuples) == 1
    assert caplog.record_tuples[0][2] == f"Exited with code: {err.exit_code}. Stderr: {err.stderr}"


def test_client_config_changed_event_when_error(
    harness, mocked_kubernetes_service_patcher, mocked_hydra_cli, caplog
):
    caplog.set_level(logging.ERROR)
    harness.begin_with_initial_hooks()
    harness.set_can_connect(CONTAINER_NAME, True)
    err = Error("Some error")
    mocked_hydra_cli.side_effect = err

    relation_id, _ = setup_oauth_relation(harness)
    harness.charm.oauth.on.client_config_changed.emit(
        relation_id=relation_id, client_id="client_id", **CLIENT_CONFIG
    )

    assert len(caplog.record_tuples) == 1
    assert (
        caplog.record_tuples[0][2] == f"Something went wrong when trying to run the command: {err}"
    )
