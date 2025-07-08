# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
from unittest.mock import MagicMock, mock_open, patch

import pytest
from ops.testing import Harness

from configs import CharmConfig, ConfigFile, ServiceConfigSource
from constants import DEFAULT_OAUTH_SCOPES


class TestCharmConfig:
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
    def test_to_service_configs(self, harness: Harness, config: dict, expected: dict) -> None:
        harness.update_config(config)
        actual = CharmConfig(harness.charm.config).to_service_configs()

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
    def test_to_env_vars(self, harness: Harness, config: dict, expected: dict) -> None:
        harness.update_config(config)
        actual = CharmConfig(harness.charm.config).to_env_vars()

        assert actual == expected


class TestConfigFile:
    @pytest.fixture
    def config_template(self) -> str:
        return "{{ supported_scopes }} and {{ key1 }} and {{ key2 }}"

    def test_from_sources(self, config_template: str) -> None:
        source = MagicMock(spec=ServiceConfigSource)
        source.to_service_configs.return_value = {"key1": "value1"}

        another_source = MagicMock(spec=ServiceConfigSource)
        another_source.to_service_configs.return_value = {"key2": "value2"}

        with patch("builtins.open", mock_open(read_data=config_template)):
            config_file = ConfigFile.from_sources(source, another_source)

        assert str(config_file) == f"{DEFAULT_OAUTH_SCOPES} and value1 and value2"
