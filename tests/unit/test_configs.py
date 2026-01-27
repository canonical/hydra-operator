# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, mock_open, patch

import pytest
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
