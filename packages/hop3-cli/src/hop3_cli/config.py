# Copyright (c) 2023-2025, Abilian SAS

from __future__ import annotations

import dataclasses
import os
from pathlib import Path
from typing import ClassVar

import toml
from platformdirs import user_config_dir

PREFIX = "HOP3_"
APP_NAME = "hop3-cli"
APP_AUTHOR = "Abilian SAS"

_marker = object()


# TODO: refactor (make is really immutable, add a ConfigLoader class)
# TODO: add support for JSON and YAML


@dataclasses.dataclass(frozen=True)
class Config:
    data: dict = dataclasses.field(default_factory=dict)

    defaults: ClassVar[dict] = {
        "api_url": "https://api.hop3.io",
        "api_version": "v1",
        "api_key": None,
        "api_secret": None,
        "server_port": 8000,
    }

    @staticmethod
    def from_dict(data: dict) -> Config:
        return Config(data)

    @staticmethod
    def from_toml_file(file: Path) -> Config:
        if not file.exists():
            raise FileNotFoundError(file)

        with file.open() as f:
            data = toml.load(f)
            return Config(data)

    def __getitem__(self, item):
        value = self.get(item)
        if value is _marker:
            raise KeyError(item)
        return value

    def get(self, key, default=_marker):
        env_var = PREFIX + key.upper()
        if env_var in os.environ:
            return os.environ[env_var]

        if key in self.data:
            return self.data[key]

        if default is not _marker:
            return default

        if key in self.defaults:
            return self.defaults[key]

        raise KeyError(key)


def get_config(config_file: Path | str | None = None) -> Config:
    if config_file is None:
        config_dir = user_config_dir(APP_NAME, APP_AUTHOR)
        config_path = Path(config_dir) / "config.toml"
    else:
        config_path = Path(config_file)
    config = Config(config_path)
    config.load_config()
    return config
