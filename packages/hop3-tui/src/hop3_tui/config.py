# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Configuration handling for Hop3 TUI."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[import-not-found]


@dataclass
class TUIConfig:
    """Configuration for the Hop3 TUI application."""

    # Server connection
    server_url: str = "http://localhost:5000"
    auth_token: str | None = None

    # Display settings
    theme: str = "dark"
    refresh_interval: int = 5
    show_clock: bool = True

    # Behavior
    auto_refresh: bool = True
    confirm_destructive: bool = True

    @classmethod
    def load(cls) -> TUIConfig:
        """Load configuration from environment and config file.

        Priority (highest to lowest):
        1. Environment variables (HOP3_*)
        2. TUI config file (~/.config/hop3/tui.toml)
        3. CLI config file (~/Library/Application Support/hop3-cli/config.toml)
        4. Default values
        """
        config = cls()

        # Load from CLI config file first (lowest priority file)
        cli_config_file = cls._find_cli_config_file()
        if cli_config_file:
            config = cls._load_from_cli_config(cli_config_file, config)

        # Load from TUI config file (overrides CLI config)
        config_file = cls._find_config_file()
        if config_file and config_file.exists():
            config = cls._load_from_file(config_file, config)

        # Override with environment variables (highest priority)
        config = cls._load_from_env(config)

        return config

    @classmethod
    def _find_config_file(cls) -> Path | None:
        """Find the configuration file."""
        # Check in order of priority
        candidates = [
            Path.cwd() / "hop3-tui.toml",
            Path.cwd() / ".hop3-tui.toml",
            Path.home() / ".config" / "hop3" / "tui.toml",
            Path.home() / ".hop3" / "tui.toml",
        ]

        for path in candidates:
            if path.exists():
                return path

        return None

    @classmethod
    def _find_cli_config_file(cls) -> Path | None:
        """Find the hop3-cli configuration file."""
        # Check platform-specific locations
        if sys.platform == "darwin":
            # macOS: ~/Library/Application Support/hop3-cli/config.toml
            cli_config = (
                Path.home()
                / "Library"
                / "Application Support"
                / "hop3-cli"
                / "config.toml"
            )
        elif sys.platform == "win32":
            # Windows: %APPDATA%/hop3-cli/config.toml
            appdata = os.environ.get("APPDATA", "")
            if appdata:
                cli_config = Path(appdata) / "hop3-cli" / "config.toml"
            else:
                cli_config = Path.home() / ".hop3-cli" / "config.toml"
        else:
            # Linux/Unix: ~/.config/hop3-cli/config.toml or ~/.hop3-cli/config.toml
            cli_config = Path.home() / ".config" / "hop3-cli" / "config.toml"
            if not cli_config.exists():
                cli_config = Path.home() / ".hop3-cli" / "config.toml"

        if cli_config.exists():
            return cli_config

        return None

    @classmethod
    def _load_from_cli_config(cls, path: Path, config: TUIConfig) -> TUIConfig:
        """Load configuration from hop3-cli config file."""
        try:
            with path.open("rb") as f:
                data = tomllib.load(f)
        except Exception:
            return config

        # CLI uses different field names
        if "api_url" in data:
            config.server_url = data["api_url"]
        if "api_token" in data:
            config.auth_token = data["api_token"]

        return config

    @classmethod
    def _load_from_file(cls, path: Path, config: TUIConfig) -> TUIConfig:
        """Load configuration from a TOML file."""
        try:
            with path.open("rb") as f:
                data = tomllib.load(f)
        except Exception:
            return config

        # Server settings
        if "server" in data:
            server = data["server"]
            if "url" in server:
                config.server_url = server["url"]
            if "token" in server:
                config.auth_token = server["token"]

        # Display settings
        if "display" in data:
            display = data["display"]
            if "theme" in display:
                config.theme = display["theme"]
            if "refresh_interval" in display:
                config.refresh_interval = display["refresh_interval"]
            if "show_clock" in display:
                config.show_clock = display["show_clock"]

        # Behavior settings
        if "behavior" in data:
            behavior = data["behavior"]
            if "auto_refresh" in behavior:
                config.auto_refresh = behavior["auto_refresh"]
            if "confirm_destructive" in behavior:
                config.confirm_destructive = behavior["confirm_destructive"]

        return config

    @classmethod
    def _load_from_env(cls, config: TUIConfig) -> TUIConfig:
        """Load configuration from environment variables."""
        # Server URL
        if (url := os.environ.get("HOP3_SERVER_URL")) or (
            url := os.environ.get("HOP3_URL")
        ):
            config.server_url = url

        # Auth token
        if (token := os.environ.get("HOP3_AUTH_TOKEN")) or (
            token := os.environ.get("HOP3_TOKEN")
        ):
            config.auth_token = token

        # Theme
        if theme := os.environ.get("HOP3_TUI_THEME"):
            config.theme = theme

        # Refresh interval
        if interval := os.environ.get("HOP3_TUI_REFRESH"):
            try:
                config.refresh_interval = int(interval)
            except ValueError:
                pass

        return config

    def save(self, path: Path | None = None) -> None:
        """Save configuration to a TOML file."""
        if path is None:
            path = Path.home() / ".config" / "hop3" / "tui.toml"

        # Ensure directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        content = f"""# Hop3 TUI Configuration

[server]
url = "{self.server_url}"
# token = "your-auth-token"  # Uncomment and set your token

[display]
theme = "{self.theme}"
refresh_interval = {self.refresh_interval}
show_clock = {str(self.show_clock).lower()}

[behavior]
auto_refresh = {str(self.auto_refresh).lower()}
confirm_destructive = {str(self.confirm_destructive).lower()}
"""

        Path(path).write_text(content)


# Global config instance (loaded lazily)
_config: TUIConfig | None = None


def get_config() -> TUIConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = TUIConfig.load()
    return _config


def reset_config() -> None:
    """Reset the global configuration (for testing)."""
    global _config
    _config = None
