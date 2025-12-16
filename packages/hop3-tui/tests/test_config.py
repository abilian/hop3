# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Tests for TUI configuration."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from hop3_tui.config import TUIConfig, get_config, reset_config


class TestTUIConfig:
    """Tests for TUIConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = TUIConfig()
        assert config.server_url == "http://localhost:5000"
        assert config.auth_token is None
        assert config.theme == "dark"
        assert config.refresh_interval == 5
        assert config.show_clock is True
        assert config.auto_refresh is True
        assert config.confirm_destructive is True

    def test_custom_values(self):
        """Test configuration with custom values."""
        config = TUIConfig(
            server_url="https://example.com:8080",
            auth_token="my-token",
            theme="light",
            refresh_interval=10,
            show_clock=False,
            auto_refresh=False,
            confirm_destructive=False,
        )
        assert config.server_url == "https://example.com:8080"
        assert config.auth_token == "my-token"
        assert config.theme == "light"
        assert config.refresh_interval == 10
        assert config.show_clock is False
        assert config.auto_refresh is False
        assert config.confirm_destructive is False


class TestConfigFromEnv:
    """Tests for loading config from environment variables."""

    def setup_method(self):
        """Clear relevant env vars before each test."""
        for var in [
            "HOP3_SERVER_URL",
            "HOP3_URL",
            "HOP3_AUTH_TOKEN",
            "HOP3_TOKEN",
            "HOP3_TUI_THEME",
            "HOP3_TUI_REFRESH",
        ]:
            if var in os.environ:
                del os.environ[var]

    def teardown_method(self):
        """Clean up env vars after each test."""
        self.setup_method()
        reset_config()

    def test_load_server_url_from_env(self):
        """Test loading server URL from environment."""
        os.environ["HOP3_SERVER_URL"] = "https://myserver.com"
        config = TUIConfig()
        config = TUIConfig._load_from_env(config)
        assert config.server_url == "https://myserver.com"

    def test_load_server_url_fallback(self):
        """Test loading server URL from HOP3_URL fallback."""
        os.environ["HOP3_URL"] = "https://fallback.com"
        config = TUIConfig()
        config = TUIConfig._load_from_env(config)
        assert config.server_url == "https://fallback.com"

    def test_load_auth_token_from_env(self):
        """Test loading auth token from environment."""
        os.environ["HOP3_AUTH_TOKEN"] = "secret-token"
        config = TUIConfig()
        config = TUIConfig._load_from_env(config)
        assert config.auth_token == "secret-token"

    def test_load_auth_token_fallback(self):
        """Test loading auth token from HOP3_TOKEN fallback."""
        os.environ["HOP3_TOKEN"] = "fallback-token"
        config = TUIConfig()
        config = TUIConfig._load_from_env(config)
        assert config.auth_token == "fallback-token"

    def test_load_theme_from_env(self):
        """Test loading theme from environment."""
        os.environ["HOP3_TUI_THEME"] = "light"
        config = TUIConfig()
        config = TUIConfig._load_from_env(config)
        assert config.theme == "light"

    def test_load_refresh_interval_from_env(self):
        """Test loading refresh interval from environment."""
        os.environ["HOP3_TUI_REFRESH"] = "15"
        config = TUIConfig()
        config = TUIConfig._load_from_env(config)
        assert config.refresh_interval == 15

    def test_invalid_refresh_interval_ignored(self):
        """Test that invalid refresh interval is ignored."""
        os.environ["HOP3_TUI_REFRESH"] = "not-a-number"
        config = TUIConfig()
        config = TUIConfig._load_from_env(config)
        # Should remain at default
        assert config.refresh_interval == 5


class TestConfigFromFile:
    """Tests for loading config from TOML file."""

    def test_load_from_nonexistent_file(self, tmp_path: Path):
        """Test loading from a file that doesn't exist."""
        config = TUIConfig()
        result = TUIConfig._load_from_file(tmp_path / "nonexistent.toml", config)
        # Should return original config unchanged
        assert result.server_url == "http://localhost:5000"

    def test_load_from_toml_file(self, tmp_path: Path):
        """Test loading from a valid TOML file."""
        config_file = tmp_path / "tui.toml"
        config_file.write_text("""
[server]
url = "https://myserver.com:8080"
token = "file-token"

[display]
theme = "light"
refresh_interval = 20
show_clock = false

[behavior]
auto_refresh = false
confirm_destructive = false
""")
        config = TUIConfig()
        result = TUIConfig._load_from_file(config_file, config)

        assert result.server_url == "https://myserver.com:8080"
        assert result.auth_token == "file-token"
        assert result.theme == "light"
        assert result.refresh_interval == 20
        assert result.show_clock is False
        assert result.auto_refresh is False
        assert result.confirm_destructive is False

    def test_load_partial_config(self, tmp_path: Path):
        """Test loading a partial config file."""
        config_file = tmp_path / "tui.toml"
        config_file.write_text("""
[server]
url = "https://partial.com"
""")
        config = TUIConfig()
        result = TUIConfig._load_from_file(config_file, config)

        # Only server URL should be changed
        assert result.server_url == "https://partial.com"
        assert result.auth_token is None  # Default
        assert result.theme == "dark"  # Default
        assert result.refresh_interval == 5  # Default

    def test_load_invalid_toml_ignored(self, tmp_path: Path):
        """Test that invalid TOML files are ignored."""
        config_file = tmp_path / "tui.toml"
        config_file.write_text("this is not valid toml {{{")
        config = TUIConfig()
        result = TUIConfig._load_from_file(config_file, config)
        # Should return original config unchanged
        assert result.server_url == "http://localhost:5000"


class TestConfigSave:
    """Tests for saving configuration to file."""

    def test_save_config(self, tmp_path: Path):
        """Test saving configuration to a file."""
        config = TUIConfig(
            server_url="https://saved.com",
            theme="light",
            refresh_interval=10,
            show_clock=False,
            auto_refresh=False,
            confirm_destructive=False,
        )
        config_path = tmp_path / "saved.toml"
        config.save(config_path)

        # Check file was created
        assert config_path.exists()

        # Check contents
        content = config_path.read_text()
        assert 'url = "https://saved.com"' in content
        assert 'theme = "light"' in content
        assert "refresh_interval = 10" in content
        assert "show_clock = false" in content
        assert "auto_refresh = false" in content
        assert "confirm_destructive = false" in content

    def test_save_creates_parent_directory(self, tmp_path: Path):
        """Test that save creates parent directories."""
        config = TUIConfig()
        config_path = tmp_path / "subdir" / "config" / "tui.toml"
        config.save(config_path)
        assert config_path.exists()


class TestFindConfigFile:
    """Tests for finding configuration file."""

    def test_find_no_config_file(self, tmp_path: Path):
        """Test when no config file exists."""
        with (
            patch("hop3_tui.config.Path.cwd", return_value=tmp_path),
            patch("hop3_tui.config.Path.home", return_value=tmp_path),
        ):
            result = TUIConfig._find_config_file()
            assert result is None

    def test_find_local_config_file(self, tmp_path: Path):
        """Test finding local config file."""
        config_file = tmp_path / "hop3-tui.toml"
        config_file.touch()

        with patch("hop3_tui.config.Path.cwd", return_value=tmp_path):
            result = TUIConfig._find_config_file()
            assert result == config_file

    def test_find_hidden_local_config_file(self, tmp_path: Path):
        """Test finding hidden local config file."""
        config_file = tmp_path / ".hop3-tui.toml"
        config_file.touch()

        with patch("hop3_tui.config.Path.cwd", return_value=tmp_path):
            result = TUIConfig._find_config_file()
            assert result == config_file


class TestCLIConfigFallback:
    """Tests for loading config from hop3-cli config file."""

    def test_load_from_cli_config(self, tmp_path: Path):
        """Test loading from a hop3-cli config file."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("""
api_url = "https://cli-server.com:8000"
api_token = "cli-token-123"
ssl_cert = "/path/to/cert.crt"
verify_ssl = "false"
""")
        config = TUIConfig()
        result = TUIConfig._load_from_cli_config(config_file, config)

        assert result.server_url == "https://cli-server.com:8000"
        assert result.auth_token == "cli-token-123"
        # Other fields should remain default
        assert result.theme == "dark"
        assert result.refresh_interval == 5

    def test_load_partial_cli_config(self, tmp_path: Path):
        """Test loading a partial CLI config file."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("""
api_url = "https://partial-cli.com"
""")
        config = TUIConfig()
        result = TUIConfig._load_from_cli_config(config_file, config)

        assert result.server_url == "https://partial-cli.com"
        assert result.auth_token is None  # Not in file, remains default

    def test_cli_config_invalid_toml_ignored(self, tmp_path: Path):
        """Test that invalid CLI config is ignored."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("invalid { toml }")
        config = TUIConfig()
        result = TUIConfig._load_from_cli_config(config_file, config)
        # Should return original config unchanged
        assert result.server_url == "http://localhost:5000"

    def test_tui_config_overrides_cli_config(self, tmp_path: Path):
        """Test that TUI config takes priority over CLI config."""
        # Create CLI config
        cli_config = tmp_path / "cli" / "config.toml"
        cli_config.parent.mkdir(parents=True)
        cli_config.write_text("""
api_url = "https://cli-server.com"
api_token = "cli-token"
""")

        # Create TUI config
        tui_config = tmp_path / "tui.toml"
        tui_config.write_text("""
[server]
url = "https://tui-server.com"
""")

        config = TUIConfig()
        # First load CLI config (lower priority)
        config = TUIConfig._load_from_cli_config(cli_config, config)
        # Then load TUI config (higher priority)
        config = TUIConfig._load_from_file(tui_config, config)

        # TUI config should override CLI config for server_url
        assert config.server_url == "https://tui-server.com"
        # But CLI token should remain (not overridden by TUI)
        assert config.auth_token == "cli-token"


class TestGetConfig:
    """Tests for get_config function."""

    def setup_method(self):
        """Reset global config before each test."""
        reset_config()

    def teardown_method(self):
        """Reset global config after each test."""
        reset_config()

    def test_get_config_returns_instance(self):
        """Test that get_config returns a TUIConfig instance."""
        config = get_config()
        assert isinstance(config, TUIConfig)

    def test_get_config_caches_result(self):
        """Test that get_config returns the same instance."""
        config1 = get_config()
        config2 = get_config()
        assert config1 is config2

    def test_reset_config_clears_cache(self):
        """Test that reset_config clears the cached config."""
        config1 = get_config()
        reset_config()
        config2 = get_config()
        # Should be a new instance (though likely equal values)
        assert config1 is not config2
