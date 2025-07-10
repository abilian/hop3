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


@dataclasses.dataclass(frozen=True)
class Config:
    data: dict = dataclasses.field(default_factory=dict)

    # These are the ultimate fallbacks if nothing is configured.
    defaults: ClassVar[dict] = {
        # Defaulting to localhost to encourage local dev first.
        # A production setup would override this in a config file or env var.
        "api_url": "http://localhost:8000",
        "api_version": "v1",
        "server_port": 8000,
        "ssh_user": "root",
        # api_key and api_secret should be managed in state, not config.
        # "api_key": None,
        # "api_secret": None,
    }

    @staticmethod
    def from_dict(data: dict) -> Config:
        return Config(data)

    @staticmethod
    def from_toml_file(file: Path) -> Config:
        if not file.exists():
            # It's okay for the config file not to exist; we'll use defaults.
            return Config({})

        with file.open() as f:
            try:
                data = toml.load(f)
                return Config(data)
            except toml.TomlDecodeError:
                # FIXME: abort instead of returning empty config?
                # Handle malformed config file gracefully.
                # You might want to log a warning here.
                return Config({})

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
