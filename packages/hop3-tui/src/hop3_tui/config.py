# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

# ruff:file-ignore[global-statement]
# `_config` is the TUI's process-global user-config singleton. Like the
# CLI's argparse Namespace, it's intrinsically global state and a DI
# container would be overkill for a single-process TUI app.

"""Configuration handling for Hop3 TUI."""

from __future__ import annotations

import contextlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import tomllib
from platformdirs import user_config_dir

#: hop3-cli's own app identity, from `hop3_cli.core.paths`. A test pins these
#: equal: if they drift, the TUI silently stops inheriting the CLI's server.
CLI_APP_NAME = "hop3-cli"
CLI_APP_AUTHOR = "Abilian SAS"


@dataclass
class TUIConfig:
    """Configuration for the Hop3 TUI application."""

    # Server connection
    #: Empty means "no server configured". hop3-cli deliberately has no default
    #: api_url either ("unconfigured state should be detected") — and a default
    #: here is not harmless: it pointed at localhost:5000, where whatever else the
    #: developer happens to be running answers, and the TUI reported that stranger's
    #: 404 as a Hop3 error.
    server_url: str = ""

    #: Set when hop3-cli is pointed at an `ssh://` server. The TUI has no SSH
    #: tunnel, so this is not a URL it can use — it is what the TUI reports
    #: instead of quietly connecting somewhere the CLI is not.
    cli_ssh_target: str = ""
    auth_token: str | None = None

    # TLS settings (mirror hop3-cli's Config; see notes/security.md §3.4.5).
    # ``verify_ssl=False`` disables certificate verification entirely;
    # ``ssl_cert`` pins a specific cert / CA bundle. The two are
    # mutually exclusive in practice — pinning a cert implies you do
    # want verification, just against a non-system trust store.
    verify_ssl: bool = True
    ssl_cert: str | None = None

    # Display settings
    theme: str = "dark"
    refresh_interval: int = 5
    show_clock: bool = True

    # Behavior
    auto_refresh: bool = True
    confirm_destructive: bool = True

    @classmethod
    def load(cls) -> TUIConfig:
        """
        Load configuration from environment and config file.

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
        """Find the hop3-cli configuration file, the way hop3-cli finds it.

        Resolved with the same `platformdirs` call and the same app name/author
        hop3-cli uses (`hop3_cli.core.paths.config_dir`), and honouring the same
        `$HOP3_CONFIG_DIR` override. This used to guess per platform and guessed
        wrong on macOS — it looked in `~/Library/Application Support/hop3-cli/`
        while the CLI was using `~/.config/hop3-cli/`. The TUI then fell back to
        its own default server and talked to whatever else was listening there.
        """
        override = os.environ.get("HOP3_CONFIG_DIR", "").strip()
        directory = (
            Path(override)
            if override
            else Path(user_config_dir(CLI_APP_NAME, CLI_APP_AUTHOR))
        )
        cli_config = directory / "config.toml"
        return cli_config if cli_config.exists() else None

    @classmethod
    def _load_from_cli_config(cls, path: Path, config: TUIConfig) -> TUIConfig:
        """Load what the TUI can use from hop3-cli's config file.

        hop3-cli resolves its server through a priority chain — the active
        context's server, then the default server, then the flat `api_url` (see
        `hop3_cli.config.Config.get_api_url`). Most of that chain points at an
        `ssh://` target, which this client cannot reach: it speaks http(s) only,
        while the CLI opens an SSH tunnel. Rather than silently reading past those
        and connecting somewhere the CLI is not, an `ssh://` target is recorded so
        the TUI can say what it found and what to do about it.
        """
        try:
            with path.open("rb") as f:
                data = tomllib.load(f)
        except Exception:
            return config

        if "api_token" in data:
            config.auth_token = data["api_token"]

        cli_section = data.get("cli", {})
        contexts = data.get("contexts", {})
        current = cli_section.get("default_context")
        server = (
            contexts.get(current, {}).get("server")
            if current
            else cli_section.get("default_server")
        ) or cli_section.get("default_server")

        if server and str(server).startswith("ssh://"):
            config.cli_ssh_target = str(server)
        elif server:
            config.server_url = str(server)
        elif "api_url" in data:
            config.server_url = data["api_url"]

        return config

    @classmethod
    def _load_from_file(cls, path: Path, config: TUIConfig) -> TUIConfig:
        """Load configuration from a TOML file."""
        try:
            with path.open("rb") as f:
                data = tomllib.load(f)
        except Exception:
            return config

        cls._load_server_settings(data, config)
        cls._load_display_settings(data, config)
        cls._load_behavior_settings(data, config)
        return config

    @classmethod
    def _load_server_settings(cls, data: dict, config: TUIConfig) -> None:
        """Load server settings from config data."""
        server = data.get("server", {})
        if url := server.get("url"):
            config.server_url = url
        if token := server.get("token"):
            config.auth_token = token
        if (verify_ssl := server.get("verify_ssl")) is not None:
            config.verify_ssl = bool(verify_ssl)
        if cert := server.get("ssl_cert"):
            config.ssl_cert = str(cert)

    @classmethod
    def _load_display_settings(cls, data: dict, config: TUIConfig) -> None:
        """Load display settings from config data."""
        display = data.get("display", {})
        if theme := display.get("theme"):
            config.theme = theme
        if (interval := display.get("refresh_interval")) is not None:
            config.refresh_interval = interval
        if (show_clock := display.get("show_clock")) is not None:
            config.show_clock = show_clock

    @classmethod
    def _load_behavior_settings(cls, data: dict, config: TUIConfig) -> None:
        """Load behavior settings from config data."""
        behavior = data.get("behavior", {})
        if (auto_refresh := behavior.get("auto_refresh")) is not None:
            config.auto_refresh = auto_refresh
        if (confirm := behavior.get("confirm_destructive")) is not None:
            config.confirm_destructive = confirm

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

        # TLS overrides (parallel to hop3-cli env handling)
        if (verify := os.environ.get("HOP3_VERIFY_SSL")) is not None:
            config.verify_ssl = verify.strip().lower() not in {
                "0",
                "false",
                "no",
                "off",
                "",
            }
        if cert := os.environ.get("HOP3_SSL_CERT"):
            config.ssl_cert = cert

        # Theme
        if theme := os.environ.get("HOP3_TUI_THEME"):
            config.theme = theme

        # Refresh interval
        if interval := os.environ.get("HOP3_TUI_REFRESH"):
            with contextlib.suppress(ValueError):
                config.refresh_interval = int(interval)

        return config

    def save(self, path: Path | None = None) -> None:
        """
        Save configuration to a TOML file.

        SECURITY: the config holds the JWT auth token. Two precautions
        identical to ``hop3-cli``'s ``Config.save`` (see
        notes/security.md §3.4.4):

        1. ``chmod 0o600`` so other local users can't read it.
        2. Atomic write via tmpfile + ``os.replace`` so a crash
           mid-write can't leave the file truncated.
        """
        if path is None:
            path = Path.home() / ".config" / "hop3" / "tui.toml"

        config_dir = path.parent
        config_dir.mkdir(parents=True, exist_ok=True)

        ssl_cert_line = f'ssl_cert = "{self.ssl_cert}"\n' if self.ssl_cert else ""
        content = f"""# Hop3 TUI Configuration

[server]
url = "{self.server_url}"
# token = "your-auth-token"  # Uncomment and set your token
verify_ssl = {str(self.verify_ssl).lower()}
{ssl_cert_line}\
[display]
theme = "{self.theme}"
refresh_interval = {self.refresh_interval}
show_clock = {str(self.show_clock).lower()}

[behavior]
auto_refresh = {str(self.auto_refresh).lower()}
confirm_destructive = {str(self.confirm_destructive).lower()}
"""

        fd, tmp_path = tempfile.mkstemp(
            prefix=".tui.toml.",
            suffix=".tmp",
            dir=config_dir,
        )
        try:
            with os.fdopen(fd, "w") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, path)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise


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
