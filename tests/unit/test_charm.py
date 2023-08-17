# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
from typing import Any, Dict, Tuple
from unittest.mock import MagicMock

import pytest
import yaml
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.pebble import ExecError
from ops.testing import Harness
from test_oauth_requirer import CLIENT_CONFIG  # type: ignore

CONTAINER_NAME = "hydra"
DB_USERNAME = "test-username"
DB_PASSWORD = "test-password"
DB_ENDPOINT = "postgresql-k8s-primary.namespace.svc.cluster.local:5432"


def setup_postgres_relation(harness: Harness) -> int:
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


def setup_ingress_relation(harness: Harness, type: str) -> int:
    relation_id = harness.add_relation(f"{type}-ingress", f"{type}-traefik")
    harness.add_relation_unit(relation_id, f"{type}-traefik/0")
    harness.update_relation_data(
        relation_id,
        f"{type}-traefik",
        {"ingress": json.dumps({"url": f"http://{type}:80/{harness.model.name}-hydra"})},
    )
    return relation_id


def setup_oauth_relation(harness: Harness) -> Tuple[int, str]:
    app_name = "requirer"
    relation_id = harness.add_relation("oauth", app_name)
    harness.add_relation_unit(relation_id, "requirer/0")
    return relation_id, app_name


def setup_peer_relation(harness: Harness) -> Tuple[int, str]:
    app_name = "hydra"
    relation_id = harness.add_relation("hydra", app_name)
    return relation_id, app_name


def setup_login_ui_relation(harness: Harness) -> tuple[int, dict]:
    relation_id = harness.add_relation("ui-endpoint-info", "identity-platform-login-ui-operator")
    harness.add_relation_unit(relation_id, "identity-platform-login-ui-operator/0")
    endpoint = f"http://public:80/{harness.model.name}-identity-platform-login-ui-operator"
    login_databag = {
        "consent_url": f"{endpoint}/consent",
        "error_url": f"{endpoint}/error",
        "index_url": f"{endpoint}/index",
        "login_url": f"{endpoint}/login",
        "oidc_error_url": f"{endpoint}/oidc_error",
        "registration_url": f"{endpoint}/registration",
        "default_url": endpoint,
    }
    harness.update_relation_data(
        relation_id,
        "identity-platform-login-ui-operator",
        login_databag,
    )
    return (relation_id, login_databag)


def setup_login_ui_without_proxy_relation(harness: Harness) -> tuple[int, dict]:
    relation_id = harness.add_relation("ui-endpoint-info", "identity-platform-login-ui-operator")
    harness.add_relation_unit(relation_id, "identity-platform-login-ui-operator/0")
    login_databag = {
        "consent_url": "",
        "error_url": "",
        "index_url": "",
        "login_url": "",
        "oidc_error_url": "",
        "registration_url": "",
        "default_url": "",
    }
    harness.update_relation_data(
        relation_id,
        "identity-platform-login-ui-operator",
        login_databag,
    )
    return (relation_id, login_databag)


def setup_loki_relation(harness: Harness) -> int:
    relation_id = harness.add_relation("logging", "loki-k8s")
    harness.add_relation_unit(relation_id, "loki-k8s/0")
    databag = {
        "promtail_binary_zip_url": json.dumps(
            {
                "amd64": {
                    "filename": "promtail-static-amd64",
                    "zipsha": "543e333b0184e14015a42c3c9e9e66d2464aaa66eca48b29e185a6a18f67ab6d",
                    "binsha": "17e2e271e65f793a9fbe81eab887b941e9d680abe82d5a0602888c50f5e0cac9",
                    "url": "https://github.com/canonical/loki-k8s-operator/releases/download/promtail-v2.5.0/promtail-static-amd64.gz",
                }
            }
        ),
    }
    unit_databag = {
        "endpoint": json.dumps(
            {
                "url": "http://loki-k8s-0.loki-k8s-endpoints.model0.svc.cluster.local:3100/loki/api/v1/push"
            }
        )
    }
    harness.update_relation_data(
        relation_id,
        "loki-k8s/0",
        unit_databag,
    )
    harness.update_relation_data(
        relation_id,
        "loki-k8s",
        databag,
    )

    return relation_id


def setup_tempo_relation(harness: Harness) -> int:
    relation_id = harness.add_relation("tracing", "tempo-k8s")
    harness.add_relation_unit(relation_id, "tempo-k8s/0")
    trace_databag = {
        "host": '"tempo-k8s-0.tempo-k8s-endpoints.namespace.svc.cluster.local"',
        "ingesters": '[{"protocol": "tempo", "port": 3200}, {"protocol": "otlp_grpc", "port": 4317}, {"protocol": "otlp_http", "port": 4318}, {"protocol": "zipkin", "port": 9411}, {"protocol": "jaeger_http_thrift", "port": 14268}, {"protocol": "jaeger_grpc", "port": 14250}]',
    }
    harness.update_relation_data(
        relation_id,
        "tempo-k8s",
        trace_databag,
    )
    return relation_id


def validate_config(expected_config: Dict[str, Any], config: Dict[str, Any]) -> None:
    secrets = config.pop("secrets")

    assert "cookie" in secrets
    assert len(secrets["cookie"]) > 0
    assert "system" in secrets
    assert len(secrets["system"]) > 0
    assert config == expected_config


def test_not_leader(harness: Harness, mocked_get_secrets: MagicMock) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    harness.set_leader(False)
    setup_peer_relation(harness)
    setup_postgres_relation(harness)

    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    assert (
        "status_set",
        "waiting",
        "Unit waiting for leadership to run the migration",
        {"is_app": False},
    ) in harness._get_backend_calls()


def test_install_without_relation(harness: Harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    assert harness.charm.unit.status == BlockedStatus("Missing required relation with postgresql")


def test_install_without_database(harness: Harness) -> None:
    db_relation_id = harness.add_relation("pg-database", "postgresql-k8s")
    harness.add_relation_unit(db_relation_id, "postgresql-k8s/0")

    harness.set_can_connect(CONTAINER_NAME, True)
    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    assert harness.charm.unit.status == WaitingStatus("Waiting for database creation")


def test_relation_data(harness: Harness, mocked_run_migration: MagicMock) -> None:
    db_relation_id = setup_postgres_relation(harness)

    relation_data = harness.get_relation_data(db_relation_id, "postgresql-k8s")
    assert relation_data["username"] == "test-username"
    assert relation_data["password"] == "test-password"
    assert relation_data["endpoints"] == "postgresql-k8s-primary.namespace.svc.cluster.local:5432"


def test_relation_departed(harness: Harness, mocked_run_migration: MagicMock) -> None:
    db_relation_id = setup_postgres_relation(harness)

    harness.remove_relation_unit(db_relation_id, "postgresql-k8s/0")
    assert harness.charm.unit.status == BlockedStatus("Missing required relation with postgresql")


def test_pebble_container_can_connect(
    harness: Harness, mocked_migration_is_needed: MagicMock
) -> None:
    setup_postgres_relation(harness)
    harness.charm.on.leader_elected.emit()
    harness.set_can_connect(CONTAINER_NAME, True)

    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    assert isinstance(harness.charm.unit.status, ActiveStatus)
    service = harness.model.unit.get_container(CONTAINER_NAME).get_service("hydra")
    assert service.is_running()


def test_pebble_container_cannot_connect(
    harness: Harness, mocked_run_migration: MagicMock
) -> None:
    harness.set_can_connect(CONTAINER_NAME, False)
    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    setup_postgres_relation(harness)

    assert harness.charm.unit.status == WaitingStatus("Waiting to connect to Hydra container")


def test_postgres_created_when_no_peers(harness: Harness, mocked_run_migration: MagicMock) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    setup_postgres_relation(harness)

    assert harness.charm.unit.status == WaitingStatus("Waiting for peer relation")


def test_postgres_created_when_migration_has_run(
    harness: Harness,
    mocked_run_migration: MagicMock,
    mocked_migration_is_needed: MagicMock,
    mocked_get_secrets: MagicMock,
) -> None:
    harness.set_leader(False)
    harness.set_can_connect(CONTAINER_NAME, True)
    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)
    setup_peer_relation(harness)

    setup_postgres_relation(harness)

    assert harness.charm.unit.status == ActiveStatus()
    mocked_run_migration.assert_not_called()


def test_update_container_config(harness: Harness, mocked_run_migration: MagicMock) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    setup_postgres_relation(harness)

    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    expected_config = {
        "dsn": f"postgres://{DB_USERNAME}:{DB_PASSWORD}@{DB_ENDPOINT}/testing_hydra",
        "log": {
            "level": "info",
            "format": "json",
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
            "consent": "http://default-url.com/consent",
            "error": "http://default-url.com/oidc_error",
            "login": "http://default-url.com/login",
            "self": {
                "issuer": "http://127.0.0.1:4444/",
                "public": "http://127.0.0.1:4444/",
            },
        },
        "webfinger": {
            "oidc_discovery": {"supported_scope": ["openid", "profile", "email", "phone"]}
        },
    }

    validate_config(expected_config, yaml.safe_load(harness.charm._render_conf_file()))


def test_on_config_changed_without_service(harness: Harness) -> None:
    setup_peer_relation(harness)
    setup_postgres_relation(harness)

    assert harness.charm.unit.status == WaitingStatus("Waiting to connect to Hydra container")


def test_on_config_changed_without_database(harness: Harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    assert harness.charm.unit.status == BlockedStatus("Missing required relation with postgresql")


def test_config_updated_on_config_changed(
    harness: Harness, mocked_run_migration: MagicMock
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)
    setup_postgres_relation(harness)

    expected_config = {
        "dsn": f"postgres://{DB_USERNAME}:{DB_PASSWORD}@{DB_ENDPOINT}/testing_hydra",
        "log": {
            "level": "info",
            "format": "json",
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
            "consent": "http://default-url.com/consent",
            "error": "http://default-url.com/oidc_error",
            "login": "http://default-url.com/login",
            "self": {
                "issuer": "http://127.0.0.1:4444/",
                "public": "http://127.0.0.1:4444/",
            },
        },
        "webfinger": {
            "oidc_discovery": {"supported_scope": ["openid", "profile", "email", "phone"]}
        },
    }

    validate_config(expected_config, yaml.safe_load(harness.charm._render_conf_file()))


@pytest.mark.parametrize("api_type,port", [("admin", "4445"), ("public", "4444")])
def test_ingress_relation_created(
    harness: Harness, mocked_fqdn: MagicMock, api_type: str, port: str
) -> None:
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


def test_config_updated_on_ingress_relation_joined(harness: Harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)

    setup_postgres_relation(harness)
    setup_ingress_relation(harness, "public")

    expected_config = {
        "dsn": f"postgres://{DB_USERNAME}:{DB_PASSWORD}@{DB_ENDPOINT}/testing_hydra",
        "log": {
            "level": "info",
            "format": "json",
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
            "consent": "http://default-url.com/consent",
            "error": "http://default-url.com/oidc_error",
            "login": "http://default-url.com/login",
            "self": {
                "issuer": "https://public/testing-hydra",
                "public": "https://public/testing-hydra",
            },
        },
        "webfinger": {
            "oidc_discovery": {"supported_scope": ["openid", "profile", "email", "phone"]}
        },
    }

    validate_config(expected_config, yaml.safe_load(harness.charm._render_conf_file()))


def test_hydra_config_on_pebble_ready_without_ingress_relation_data(
    harness: Harness, mocked_migration_is_needed: MagicMock
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)

    # set relation without data
    relation_id = harness.add_relation("public-ingress", "public-traefik")
    harness.add_relation_unit(relation_id, "public-traefik/0")

    setup_peer_relation(harness)
    setup_postgres_relation(harness)
    harness.charm.on.leader_elected.emit()
    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    expected_config = {
        "dsn": f"postgres://{DB_USERNAME}:{DB_PASSWORD}@{DB_ENDPOINT}/testing_hydra",
        "log": {
            "level": "info",
            "format": "json",
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
            "consent": "http://default-url.com/consent",
            "error": "http://default-url.com/oidc_error",
            "login": "http://default-url.com/login",
            "self": {
                "issuer": "http://127.0.0.1:4444/",
                "public": "http://127.0.0.1:4444/",
            },
        },
        "webfinger": {
            "oidc_discovery": {"supported_scope": ["openid", "profile", "email", "phone"]}
        },
    }

    container = harness.model.unit.get_container(CONTAINER_NAME)
    container_config = container.pull(path="/etc/config/hydra.yaml", encoding="utf-8")
    validate_config(expected_config, yaml.safe_load(container_config))


def test_hydra_endpoint_info_relation_data_without_ingress_relation_data(harness: Harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)

    # set relations without data
    public_ingress_relation_id = harness.add_relation("public-ingress", "public-traefik")
    harness.add_relation_unit(public_ingress_relation_id, "public-traefik/0")
    admin_ingress_relation_id = harness.add_relation("admin-ingress", "admin-traefik")
    harness.add_relation_unit(admin_ingress_relation_id, "admin-traefik/0")

    hydra_endpoint_info_relation_id = harness.add_relation("hydra-endpoint-info", "kratos")
    harness.add_relation_unit(hydra_endpoint_info_relation_id, "kratos/0")

    expected_data = {
        "admin_endpoint": "http://hydra.testing.svc.cluster.local:4445",
        "public_endpoint": "http://hydra.testing.svc.cluster.local:4444",
    }

    assert harness.get_relation_data(hydra_endpoint_info_relation_id, "hydra") == expected_data


def test_provider_info_in_databag_when_ingress_then_oauth_relation(
    harness: Harness, mocked_set_provider_info: MagicMock
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)

    setup_ingress_relation(harness, "public")
    setup_ingress_relation(harness, "admin")
    setup_oauth_relation(harness)

    mocked_set_provider_info.assert_called_with(
        authorization_endpoint="https://public/testing-hydra/oauth2/auth",
        introspection_endpoint="https://admin/testing-hydra/admin/oauth2/introspect",
        issuer_url="https://public/testing-hydra",
        jwks_endpoint="https://public/testing-hydra/.well-known/jwks.json",
        scope="openid profile email phone",
        token_endpoint="https://public/testing-hydra/oauth2/token",
        userinfo_endpoint="https://public/testing-hydra/userinfo",
    )


def test_provider_info_called_when_oauth_relation_then_ingress(
    harness: Harness, mocked_set_provider_info: MagicMock
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)

    setup_oauth_relation(harness)
    setup_ingress_relation(harness, "public")
    setup_ingress_relation(harness, "admin")

    mocked_set_provider_info.assert_called_once_with(
        authorization_endpoint="https://public/testing-hydra/oauth2/auth",
        introspection_endpoint="https://admin/testing-hydra/admin/oauth2/introspect",
        issuer_url="https://public/testing-hydra",
        jwks_endpoint="https://public/testing-hydra/.well-known/jwks.json",
        scope="openid profile email phone",
        token_endpoint="https://public/testing-hydra/oauth2/token",
        userinfo_endpoint="https://public/testing-hydra/userinfo",
    )


def test_client_created_event_emitted(
    harness: Harness,
    mocked_create_client: MagicMock,
    mocked_set_client_credentials: MagicMock,
    mocked_hydra_is_running: MagicMock,
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    client_credentials = mocked_create_client.return_value
    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    peer_relation_id, _ = setup_peer_relation(harness)
    relation_id, _ = setup_oauth_relation(harness)

    harness.charm.oauth.on.client_created.emit(relation_id=relation_id, **CLIENT_CONFIG)
    peer_data = harness.get_relation_data(peer_relation_id, harness.charm.app)

    assert peer_data
    mocked_set_client_credentials.assert_called_once_with(
        relation_id, client_credentials["client_id"], client_credentials["client_secret"]
    )


def test_client_created_event_emitted_without_peers(
    harness: Harness,
    mocked_create_client: MagicMock,
    mocked_set_client_credentials: MagicMock,
    mocked_hydra_is_running: MagicMock,
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    relation_id, _ = setup_oauth_relation(harness)

    harness.charm.oauth.on.client_created.emit(relation_id=relation_id, **CLIENT_CONFIG)

    assert not mocked_set_client_credentials.called


def test_client_created_event_emitted_cannot_connect(
    harness: Harness, mocked_create_client: MagicMock
) -> None:
    harness.set_can_connect(CONTAINER_NAME, False)

    relation_id, _ = setup_oauth_relation(harness)
    harness.charm.oauth.on.client_created.emit(relation_id=relation_id, **CLIENT_CONFIG)

    assert not mocked_create_client.called


def test_client_created_event_emitted_without_service(
    harness: Harness, mocked_create_client: MagicMock
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)

    relation_id, _ = setup_oauth_relation(harness)
    harness.charm.oauth.on.client_created.emit(relation_id=relation_id, **CLIENT_CONFIG)

    assert not mocked_create_client.called


def test_exec_error_on_client_created_event_emitted(
    harness: Harness,
    mocked_create_client: MagicMock,
    mocked_hydra_is_running: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)
    harness.set_can_connect(CONTAINER_NAME, True)
    setup_peer_relation(harness)
    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)
    err = ExecError(
        command=["hydra", "create", "client", "1234"], exit_code=1, stdout="Out", stderr="Error"
    )
    mocked_create_client.side_effect = err

    relation_id, _ = setup_oauth_relation(harness)
    harness.charm.oauth.on.client_created.emit(relation_id=relation_id, **CLIENT_CONFIG)

    error_messages = [record[2] for record in caplog.record_tuples]
    assert f"Exited with code: {err.exit_code}. Stderr: {err.stderr}" in error_messages


def test_client_changed_event_emitted(
    harness: Harness, mocked_update_client: MagicMock, mocked_hydra_is_running: MagicMock
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    relation_id, _ = setup_oauth_relation(harness)
    harness.charm.oauth.on.client_changed.emit(
        relation_id=relation_id, client_id="client_id", **CLIENT_CONFIG
    )

    assert mocked_update_client.called


def test_client_changed_event_emitted_cannot_connect(
    harness: Harness, mocked_update_client: MagicMock
) -> None:
    harness.set_can_connect(CONTAINER_NAME, False)

    relation_id, _ = setup_oauth_relation(harness)
    harness.charm.oauth.on.client_changed.emit(
        relation_id=relation_id, client_id="client_id", **CLIENT_CONFIG
    )

    assert not mocked_update_client.called


def test_client_changed_event_emitted_without_service(
    harness: Harness, mocked_update_client: MagicMock
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)

    relation_id, _ = setup_oauth_relation(harness)
    harness.charm.oauth.on.client_changed.emit(
        relation_id=relation_id, client_id="client_id", **CLIENT_CONFIG
    )

    assert not mocked_update_client.called


def test_exec_error_on_client_changed_event_emitted(
    harness: Harness,
    mocked_update_client: MagicMock,
    mocked_hydra_is_running: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)
    harness.set_can_connect(CONTAINER_NAME, True)
    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)
    err = ExecError(
        command=["hydra", "create", "client", "1234"], exit_code=1, stdout="Out", stderr="Error"
    )
    mocked_update_client.side_effect = err

    relation_id, _ = setup_oauth_relation(harness)
    harness.charm.oauth.on.client_changed.emit(
        relation_id=relation_id, client_id="client_id", **CLIENT_CONFIG
    )

    error_messages = [record[2] for record in caplog.record_tuples]
    assert f"Exited with code: {err.exit_code}. Stderr: {err.stderr}" in error_messages


def test_client_deleted_event_emitted(
    harness: Harness,
    mocked_create_client: MagicMock,
    mocked_delete_client: MagicMock,
    mocked_hydra_is_running: MagicMock,
) -> None:
    client_id = mocked_delete_client.return_value
    harness.set_can_connect(CONTAINER_NAME, True)
    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    peer_relation_id, _ = setup_peer_relation(harness)
    relation_id, _ = setup_oauth_relation(harness)
    harness.charm.oauth.on.client_created.emit(relation_id=relation_id, **CLIENT_CONFIG)

    harness.charm.oauth.on.client_deleted.emit(relation_id)

    mocked_delete_client.assert_called_with(client_id)
    assert harness.get_relation_data(peer_relation_id, harness.charm.app) == {}


def test_client_deleted_event_emitted_without_peers(
    harness: Harness,
    mocked_create_client: MagicMock,
    mocked_delete_client: MagicMock,
    mocked_hydra_is_running: MagicMock,
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)

    relation_id, _ = setup_oauth_relation(harness)
    harness.charm.oauth.on.client_created.emit(relation_id=relation_id, **CLIENT_CONFIG)

    harness.charm.oauth.on.client_deleted.emit(relation_id)

    assert not mocked_delete_client.called


def test_client_deleted_event_emitted_cannot_connect(
    harness: Harness, mocked_delete_client: MagicMock
) -> None:
    harness.set_can_connect(CONTAINER_NAME, False)

    relation_id, _ = setup_oauth_relation(harness)
    harness.charm.oauth.on.client_deleted.emit(relation_id)

    assert not mocked_delete_client.called


def test_client_deleted_event_emitted_without_service(
    harness: Harness, mocked_delete_client: MagicMock
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)

    relation_id, _ = setup_oauth_relation(harness)
    harness.charm.oauth.on.client_deleted.emit(relation_id)

    assert not mocked_delete_client.called


def test_exec_error_on_client_deleted_event_emitted(
    harness: Harness,
    mocked_create_client: MagicMock,
    mocked_delete_client: MagicMock,
    mocked_hydra_is_running: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)
    harness.set_can_connect(CONTAINER_NAME, True)
    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)
    err = ExecError(
        command=["hydra", "delete", "client", "1234"], exit_code=1, stdout="Out", stderr="Error"
    )
    mocked_delete_client.side_effect = err
    setup_peer_relation(harness)
    relation_id, _ = setup_oauth_relation(harness)
    harness.charm.oauth.on.client_created.emit(relation_id=relation_id, **CLIENT_CONFIG)

    harness.charm.oauth.on.client_deleted.emit(relation_id)

    error_messages = [record[2] for record in caplog.record_tuples]
    assert f"Exited with code: {err.exit_code}. Stderr: {err.stderr}" in error_messages


def test_config_updated_without_login_ui_endpoints_interface(
    harness: Harness, mocked_run_migration: MagicMock
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    harness.charm.on.leader_elected.emit()
    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)
    setup_peer_relation(harness)
    setup_postgres_relation(harness)

    expected_config = {
        "dsn": f"postgres://{DB_USERNAME}:{DB_PASSWORD}@{DB_ENDPOINT}/testing_hydra",
        "log": {
            "level": "info",
            "format": "json",
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
            "consent": "http://default-url.com/consent",
            "error": "http://default-url.com/oidc_error",
            "login": "http://default-url.com/login",
            "self": {
                "issuer": "http://127.0.0.1:4444/",
                "public": "http://127.0.0.1:4444/",
            },
        },
        "webfinger": {
            "oidc_discovery": {"supported_scope": ["openid", "profile", "email", "phone"]}
        },
    }

    container_config = harness.charm._container.pull(
        path="/etc/config/hydra.yaml", encoding="utf-8"
    )
    validate_config(expected_config, yaml.safe_load(container_config.read()))


def test_config_updated_with_login_ui_endpoints_interface(
    harness: Harness, mocked_migration_is_needed: MagicMock
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    harness.charm.on.leader_elected.emit()
    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)
    setup_postgres_relation(harness)
    (_, login_databag) = setup_login_ui_relation(harness)

    expected_config = {
        "dsn": f"postgres://{DB_USERNAME}:{DB_PASSWORD}@{DB_ENDPOINT}/testing_hydra",
        "log": {
            "level": "info",
            "format": "json",
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
            "consent": login_databag["consent_url"],
            "error": login_databag["oidc_error_url"],
            "login": login_databag["login_url"],
            "self": {
                "issuer": "http://127.0.0.1:4444/",
                "public": "http://127.0.0.1:4444/",
            },
        },
        "webfinger": {
            "oidc_discovery": {"supported_scope": ["openid", "profile", "email", "phone"]}
        },
    }

    container_config = harness.charm._container.pull(
        path="/etc/config/hydra.yaml", encoding="utf-8"
    )
    validate_config(expected_config, yaml.safe_load(container_config.read()))


def test_config_updated_with_login_ui_endpoints_proxy_down_interface(
    harness: Harness, mocked_migration_is_needed: MagicMock
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    harness.charm.on.leader_elected.emit()
    harness.charm.on.hydra_pebble_ready.emit(CONTAINER_NAME)
    setup_peer_relation(harness)
    setup_postgres_relation(harness)
    setup_login_ui_without_proxy_relation(harness)

    expected_config = {
        "dsn": f"postgres://{DB_USERNAME}:{DB_PASSWORD}@{DB_ENDPOINT}/testing_hydra",
        "log": {
            "level": "info",
            "format": "json",
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
            "consent": "http://default-url.com/consent",
            "error": "http://default-url.com/oidc_error",
            "login": "http://default-url.com/login",
            "self": {
                "issuer": "http://127.0.0.1:4444/",
                "public": "http://127.0.0.1:4444/",
            },
        },
        "webfinger": {
            "oidc_discovery": {"supported_scope": ["openid", "profile", "email", "phone"]}
        },
    }

    container_config = harness.charm._container.pull(
        path="/etc/config/hydra.yaml", encoding="utf-8"
    )
    validate_config(expected_config, yaml.safe_load(container_config.read()))


@pytest.mark.parametrize(
    "action",
    [
        "_on_create_oauth_client_action",
        "_on_get_oauth_client_info_action",
        "_on_update_oauth_client_action",
        "_on_delete_oauth_client_action",
        "_on_list_oauth_clients_action",
        "_on_revoke_oauth_client_access_tokens_action",
        "_on_rotate_key_action",
    ],
)
def test_actions_when_cannot_connect(harness: Harness, action: str) -> None:
    harness.set_can_connect(CONTAINER_NAME, False)
    event = MagicMock()

    getattr(harness.charm, action)(event)

    event.fail.assert_called_with(
        "Service is not ready. Please re-run the action when the charm is active"
    )


def test_create_oauth_client_action(
    harness: Harness, mocked_hydra_is_running: MagicMock, mocked_create_client: MagicMock
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    event = MagicMock()
    event.params = {}

    harness.charm._on_create_oauth_client_action(event)

    ret = mocked_create_client.return_value
    event.set_results.assert_called_with(
        {
            "client-id": ret.get("client_id"),
            "client-secret": ret.get("client_secret"),
            "audience": ret.get("audience"),
            "grant-types": ", ".join(ret.get("grant_types")),
            "redirect-uris": ", ".join(ret.get("redirect_uris")),
            "response-types": ", ".join(ret.get("response_types")),
            "scope": ret.get("scope"),
            "token-endpoint-auth-method": ret.get("token_endpoint_auth_method"),
        }
    )


def test_get_oauth_client_info_action(
    harness: Harness, mocked_hydra_is_running: MagicMock, mocked_get_client: MagicMock
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    ret = mocked_get_client.return_value
    event = MagicMock()
    event.params = {
        "client-id": ret.get("client_id"),
    }

    harness.charm._on_get_oauth_client_info_action(event)

    event.set_results.assert_called_with(
        {k.replace("_", "-"): ", ".join(v) if isinstance(v, list) else v for k, v in ret.items()}
    )


def test_update_oauth_client_action(
    harness: Harness,
    mocked_hydra_is_running: MagicMock,
    mocked_update_client: MagicMock,
    mocked_get_client: MagicMock,
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    ret = mocked_update_client.return_value
    event = MagicMock()
    event.params = {
        "client-id": ret.get("client_id"),
    }

    harness.charm._on_update_oauth_client_action(event)

    event.set_results.assert_called_with(
        {
            "client-id": ret.get("client_id"),
            "client-secret": ret.get("client_secret"),
            "audience": ret.get("audience"),
            "grant-types": ", ".join(ret.get("grant_types")),
            "redirect-uris": ", ".join(ret.get("redirect_uris")),
            "response-types": ", ".join(ret.get("response_types")),
            "scope": ret.get("scope"),
            "token-endpoint-auth-method": ret.get("token_endpoint_auth_method"),
        }
    )


def test_update_oauth_client_action_when_oauth_relation_client(
    harness: Harness,
    mocked_hydra_is_running: MagicMock,
    mocked_update_client: MagicMock,
    mocked_get_client: MagicMock,
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    ret = mocked_update_client.return_value
    event = MagicMock()
    event.params = {
        "client-id": ret.get("client_id"),
    }
    mocked_get_client.return_value["metadata"]["relation_id"] = 123

    harness.charm._on_update_oauth_client_action(event)

    event.fail.assert_called_with(
        f"Cannot update client `{ret.get('client_id')}`, " "it is managed from an oauth relation."
    )


def test_delete_oauth_client_action(
    harness: Harness,
    mocked_hydra_is_running: MagicMock,
    mocked_delete_client: MagicMock,
    mocked_get_client: MagicMock,
) -> None:
    client_id = "client_id"
    harness.set_can_connect(CONTAINER_NAME, True)
    event = MagicMock()
    event.params = {
        "client-id": client_id,
    }

    harness.charm._on_delete_oauth_client_action(event)

    event.set_results.assert_called_with({"client-id": client_id})


def test_delete_oauth_client_action_when_oauth_relation_client(
    harness: Harness,
    mocked_hydra_is_running: MagicMock,
    mocked_delete_client: MagicMock,
    mocked_get_client: MagicMock,
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    client_id = mocked_delete_client.return_value
    event = MagicMock()
    event.params = {
        "client-id": client_id,
    }
    mocked_get_client.return_value["metadata"]["relation_id"] = 123

    harness.charm._on_delete_oauth_client_action(event)

    event.fail.assert_called_with(
        f"Cannot delete client `{client_id}`, "
        "it is managed from an oauth relation. "
        "To delete it, remove the relation."
    )


def test_list_oauth_client_action(
    harness: Harness, mocked_hydra_is_running: MagicMock, mocked_list_client: MagicMock
) -> None:
    client_id = "client_id"
    harness.set_can_connect(CONTAINER_NAME, True)
    event = MagicMock()
    event.params = {
        "client-id": client_id,
    }

    harness.charm._on_list_oauth_clients_action(event)

    ret = mocked_list_client.return_value
    expected_output = {i["client_id"] for i in ret["items"]}
    assert set(event.set_results.call_args_list[0][0][0].values()) == expected_output


def test_revoke_oauth_client_access_tokens_action(
    harness: Harness, mocked_hydra_is_running: MagicMock, mocked_revoke_tokens: MagicMock
) -> None:
    client_id = "client_id"
    harness.set_can_connect(CONTAINER_NAME, True)
    event = MagicMock()
    event.params = {
        "client-id": client_id,
    }

    harness.charm._on_revoke_oauth_client_access_tokens_action(event)

    event.set_results.assert_called_with({"client-id": client_id})


def test_rotate_key_action(
    harness: Harness, mocked_hydra_is_running: MagicMock, mocked_create_jwk: MagicMock
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    ret = mocked_create_jwk.return_value
    event = MagicMock()
    event.params = {"alg": "SHA256"}

    harness.charm._on_rotate_key_action(event)

    event.set_results.assert_called_with({"new-key-id": ret["keys"][0]["kid"]})


def test_on_pebble_ready_with_loki(
    harness: Harness, mocked_migration_is_needed: MagicMock
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    setup_postgres_relation(harness)
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.leader_elected.emit()
    harness.charm.on.hydra_pebble_ready.emit(container)

    setup_loki_relation(harness)

    assert harness.model.unit.status == ActiveStatus()


def test_on_pebble_ready_with_bad_config(harness: Harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    setup_postgres_relation(harness)
    harness.update_config({"log_level": "invalid_config"})
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.hydra_pebble_ready.emit(container)

    assert isinstance(harness.model.unit.status, BlockedStatus)
    assert "Invalid configuration value for log_level" in harness.charm.unit.status.message


def test_on_config_changed_with_invalid_log_level(harness: Harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    setup_postgres_relation(harness)
    harness.update_config({"log_level": "invalid_config"})

    assert isinstance(harness.model.unit.status, BlockedStatus)
    assert "Invalid configuration value for log_level" in harness.charm.unit.status.message


def test_on_pebble_ready_make_dir_called(harness: Harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.hydra_pebble_ready.emit(container)
    assert container.isdir("/var/log")


def test_verify_pebble_layer_tempo_k8s(harness: Harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.hydra_pebble_ready.emit(container)
    setup_tempo_relation(harness)

    expected_layer = {
        "summary": "hydra-operator layer",
        "description": "pebble config layer for hydra-operator",
        "services": {
            "hydra": {
                "override": "replace",
                "summary": "entrypoint of the hydra-operator image",
                "command": '/bin/sh -c "hydra serve all --config /etc/config/hydra.yaml --dev 2>&1 | tee -a /var/log/hydra.log"',
                "startup": "disabled",
                "environment": {
                    "TRACING_PROVIDER": "otel",
                    "TRACING_PROVIDERS_OTLP_SERVER_URL": "tempo-k8s-0.tempo-k8s-endpoints.namespace.svc.cluster.local:4318",
                    "TRACING_PROVIDERS_OTLP_INSECURE": "true",
                    "TRACING_PROVIDERS_OTLP_SAMPLING_SAMPLING_RATIO": "1.0",
                },
            }
        },
        "checks": {
            "version": {
                "override": "replace",
                "exec": {"command": "hydra version"},
            },
            "ready": {
                "override": "replace",
                "http": {"url": "http://localhost:4445/health/ready"},
            },
        },
    }

    assert harness.charm._hydra_layer.to_dict() == expected_layer
