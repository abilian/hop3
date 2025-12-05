# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

import dataclasses
import os
from pathlib import Path
from typing import ClassVar

import toml
from platformdirs import user_config_dir

# The prefix for all environment variables.
PREFIX = "HOP3_"

APP_NAME = "hop3-cli"
APP_AUTHOR = "Abilian SAS"

_marker = object()


@dataclasses.dataclass
class Config:
    data: dict = dataclasses.field(default_factory=dict)
    config_file: Path | None = None

    # These are the ultimate fallbacks if nothing is configured.
    defaults: ClassVar[dict] = {
        # No default api_url - unconfigured state should be detected
        # Developers should set HOP3_DEV_MODE=true for localhost defaults
        "api_version": "v1",
        "server_port": 8000,
        "ssh_user": "root",
        "api_token": "",  # Bearer token for authentication
        # api_key and api_secret should be managed in state, not config.
        # "api_key": None,
        # "api_secret": None,
    }

    def is_configured(self) -> bool:
        """Check if the CLI has been configured with a server URL.

        Returns True if api_url is set via:
        1. Environment variable (HOP3_API_URL)
        2. Config file
        3. Developer mode (HOP3_DEV_MODE=true enables localhost:8000)

        Returns False if no server has been configured.
        """
        # Check for developer mode
        if os.environ.get("HOP3_DEV_MODE", "").lower() in {"true", "1", "yes"}:
            return True

        # Check environment variable
        if "HOP3_API_URL" in os.environ:
            return True

        # Check config file
        return "api_url" in self.data

    def is_authenticated(self) -> bool:
        """Check if the CLI has authentication credentials.

        Returns True if api_token is set via:
        1. Environment variable (HOP3_API_TOKEN)
        2. Config file

        Returns False if no authentication token is available.
        """
        # Check environment variable
        if os.environ.get("HOP3_API_TOKEN"):
            return True

        # Check config file
        token = self.data.get("api_token", "")
        return bool(token)

    def get_api_url(self) -> str | None:
        """Get the API URL if configured, None otherwise.

        For developers: Set HOP3_DEV_MODE=true to use localhost:8000
        """
        # Check for developer mode first
        if os.environ.get("HOP3_DEV_MODE", "").lower() in {"true", "1", "yes"}:
            # In dev mode, default to localhost but allow override
            return self.get("api_url", "http://localhost:8000")

        # Check environment variable
        if "HOP3_API_URL" in os.environ:
            return os.environ["HOP3_API_URL"]

        # Check config file
        if "api_url" in self.data:
            return self.data["api_url"]

        return None

    @staticmethod
    def from_dict(data: dict) -> Config:
        return Config(data=data)

    @staticmethod
    def from_toml_file(file: Path) -> Config:
        if not file.exists():
            # It's okay for the config file not to exist; we'll use defaults.
            return Config(data={}, config_file=file)

        with file.open() as f:
            try:
                data = toml.load(f)
                return Config(data=data, config_file=file)
            except toml.TomlDecodeError:
                # FIXME: abort instead of returning empty config?
                # Handle malformed config file gracefully.
                # You might want to log a warning here.
                return Config(data={}, config_file=file)

    def __getitem__(self, item):
        value = self.get(item)
        if value is _marker:
            raise KeyError(item)
        return value

    def get(self, key, default=_marker):
        """
        Retrieves a configuration value with a clear priority order.

        1. Environment Variable (e.g., HOP3_API_URL)
        2. Value from config file (e.g., api_url = "...")
        3. Provided default value for this method call.
        4. Class-level default value.
        """
        # 1. Check Environment Variable
        env_var_key = PREFIX + key.upper()
        if env_var_key in os.environ:
            return os.environ[env_var_key]

        # 2. Check value from config file data
        if key in self.data:
            return self.data[key]

        # 3. Check for a default value passed to this specific `get` call
        if default is not _marker:
            return default

        # 4. Check for a class-level default value
        if key in self.defaults:
            return self.defaults[key]

        # If not found anywhere, raise KeyError
        raise KeyError(key)

    def save(self, updates: dict | None = None) -> None:
        """Save the config to the TOML file.

        Args:
            updates: Optional dictionary of updates to merge into config before saving
        """
        if not self.config_file:
            msg = "Cannot save: config_file path not set"
            raise ValueError(msg)

        # Merge updates into data
        if updates:
            self.data.update(updates)

        # Ensure parent directory exists
        self.config_file.parent.mkdir(parents=True, exist_ok=True)

        # Write to file
        with self.config_file.open("w") as f:
            toml.dump(self.data, f)


def get_config(config_file: Path | str | None = None) -> Config:
    """
    Loads configuration from the standard user location or a specified file.
    """
    if config_file is None:
        # Use platform-specific user config directory
        config_dir = user_config_dir(APP_NAME, APP_AUTHOR)
        config_path = Path(config_dir) / "config.toml"
    else:
        config_path = Path(config_file)

    # Create directory if it doesn't exist to be user-friendly on first run
    config_path.parent.mkdir(parents=True, exist_ok=True)

    config = Config.from_toml_file(config_path)
    return config
