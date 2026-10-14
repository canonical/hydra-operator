# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, mock_open, patch

import pytest
import yaml
from ops import Model
from ops.pebble import PathError

from configs import CharmConfig, ConfigFile, ServiceConfigSource
from constants import DEFAULT_OAUTH_SCOPES


class TestCharmConfig:
    """Tests for the CharmConfig class."""

    @pytest.mark.parametrize(
        "config, expected",
        [
            (
                {"dev": True, "log_level": "debug", "jwt_access_tokens": True},
                {"dev_mode": True, "log_level": "debug", "access_token_strategy": "jwt"},
            ),
            (
                {"dev": False, "log_level": "info", "jwt_access_tokens": False},
                {"dev_mode": False, "log_level": "info", "access_token_strategy": "opaque"},
            ),
        ],
    )
    def test_to_service_configs(self, config: dict, expected: dict) -> None:
        """Test that charm configuration is correctly converted to service configs."""
        mock_model = MagicMock(spec=Model)
        actual = CharmConfig(config, mock_model).to_service_configs()
        assert actual == expected

    @pytest.mark.parametrize(
        "config, expected",
        [
            (
                {"dev": True},
                {"DEV": "true"},
            ),
            (
                {"dev": False},
                {"DEV": "false"},
            ),
        ],
    )
    def test_to_env_vars(self, config: dict, expected: dict) -> None:
        """Test that charm configuration is correctly converted to environment variables."""
        mock_model = MagicMock(spec=Model)
        actual = CharmConfig(config, mock_model).to_env_vars()
        assert actual == expected

    @pytest.mark.parametrize(
        "config, expected",
        [
            (
                {"use_ingress_for_relations": True},
                True,
            ),
            (
                {"use_ingress_for_relations": False},
                False,
            ),
            (
                {},
                False,
            ),
        ],
    )
    def test_use_ingress_for_relations(self, config: dict, expected: bool) -> None:
        """Test that use_ingress_for_relations config property behaves as expected."""
        mock_model = MagicMock(spec=Model)
        actual = CharmConfig(config, mock_model).use_ingress_for_relations
        assert actual == expected

    @pytest.mark.parametrize(
        "config, expected",
        [
            ({}, ""),
            ({"public_path_prefix": "sso"}, "/sso"),
            ({"public_path_prefix": "/a/b/"}, "/a/b"),
        ],
    )
    def test_public_path_prefix(self, config: dict, expected: str) -> None:
        """Test that the prefix has one leading slash and no trailing slash."""
        actual = CharmConfig(config, MagicMock(spec=Model)).public_path_prefix
        assert actual == expected


class TestConfigFile:
    """Tests for the ConfigFile class."""

    @pytest.fixture
    def config_template(self) -> str:
        return "{{ supported_scopes }} and {{ key1 }} and {{ key2 }}"

    def test_from_sources(self, config_template: str) -> None:
        """Test creating a ConfigFile from multiple sources.

        Verifies that:
        - Defaults are applied.
        - Values from sources are substituted into the template.
        """
        source = MagicMock(spec=ServiceConfigSource)
        source.to_service_configs.return_value = {"key1": "value1"}

        another_source = MagicMock(spec=ServiceConfigSource)
        another_source.to_service_configs.return_value = {"key2": "value2"}

        with patch("builtins.open", mock_open(read_data=config_template)):
            config_file = ConfigFile.from_sources(source, another_source)

        assert str(config_file) == f"{DEFAULT_OAUTH_SCOPES} and value1 and value2"

    @pytest.fixture
    def login_ui_service_configs(self) -> dict:
        return {
            "consent_url": "https://login-ui.example.com/consent",
            "oidc_error_url": "https://login-ui.example.com/oidc_error",
            "login_url": "https://login-ui.example.com/login",
            "device_verification_url": "https://login-ui.example.com/device_verification",
            "post_device_done_url": "https://login-ui.example.com/post_device_done",
        }

    def test_from_sources_with_device_urls(self, login_ui_service_configs: dict) -> None:
        """Test that Hydra is given the device flow URLs the login UI publishes."""
        source = MagicMock(spec=ServiceConfigSource)
        source.to_service_configs.return_value = login_ui_service_configs

        config_file = ConfigFile.from_sources(source)

        assert yaml.safe_load(str(config_file))["urls"]["device"] == {
            "verification": "https://login-ui.example.com/device_verification",
            "success": "https://login-ui.example.com/post_device_done",
        }

    def test_from_sources_without_device_urls(self, login_ui_service_configs: dict) -> None:
        """Test that Hydra's device flow URLs are left unset when the login UI has none.

        Hydra then falls back to its own pages; an empty or null value is not unset.
        """
        source = MagicMock(spec=ServiceConfigSource)
        source.to_service_configs.return_value = {
            **login_ui_service_configs,
            "device_verification_url": "",
            "post_device_done_url": "",
        }

        config_file = ConfigFile.from_sources(source)

        urls = yaml.safe_load(str(config_file))["urls"]
        assert "device" not in urls
        assert urls["login"] == "https://login-ui.example.com/login"

    @pytest.mark.parametrize(
        "missing, expected",
        [
            (
                "device_verification_url",
                {"success": "https://login-ui.example.com/post_device_done"},
            ),
            (
                "post_device_done_url",
                {"verification": "https://login-ui.example.com/device_verification"},
            ),
        ],
    )
    def test_from_sources_with_one_device_url(
        self, login_ui_service_configs: dict, missing: str, expected: dict
    ) -> None:
        """Test that each device flow URL is set on its own."""
        source = MagicMock(spec=ServiceConfigSource)
        source.to_service_configs.return_value = {**login_ui_service_configs, missing: ""}

        config_file = ConfigFile.from_sources(source)

        assert yaml.safe_load(str(config_file))["urls"]["device"] == expected

    @pytest.mark.parametrize(
        "session_cookie_path, expected",
        [("/sso", {"paths": {"session": "/sso"}}), ("", None)],
    )
    def test_from_sources_session_cookie_path(
        self, session_cookie_path: str, expected: dict | None
    ) -> None:
        """Test that Hydra's session cookie is kept to the path prefix, when there is one."""
        source = MagicMock(spec=ServiceConfigSource)
        source.to_service_configs.return_value = {"session_cookie_path": session_cookie_path}

        config_file = ConfigFile.from_sources(source)

        assert yaml.safe_load(str(config_file))["serve"].get("cookies") == expected

    def test_from_workload_container(self, mocked_container: MagicMock) -> None:
        """Test creating a ConfigFile from a workload container file."""
        mocked_file = MagicMock()
        mocked_file.__enter__.return_value.read.return_value = "config file"
        mocked_container.pull = MagicMock(return_value=mocked_file)

        config_file = ConfigFile.from_workload_container(mocked_container)

        assert config_file.content == "config file"

    def test_from_workload_container_non_existing_file(self, mocked_container: MagicMock) -> None:
        """Test behavior when the config file does not exist in the workload container."""
        mocked_container.pull = MagicMock(side_effect=PathError(kind="", message=""))

        config_file = ConfigFile.from_workload_container(mocked_container)

        assert not config_file.content
