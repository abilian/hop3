# Copyright (c) 2024, Abilian SAS

# ruff: noqa: N802, PLR0904

"""
Global configuration for the Hop3 Micro-PaaS Agent.

By default,
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import toml


@dataclass
class Config:
    _home: Path = Path("/home/hop3")
    _user: str = "hop3"
    _config: dict[str, Any] = field(default_factory=dict)

    def set_home(self, home: Path | str):
        home = Path(home)
        self._home = home

    def read_toml(self, path: Path):
        self._config = toml.load(path)

    def set_user(self, user: str):
        self._user = user

    def get(self, item, default=""):
        value = self._config["hop3"]
        for key in item.split("."):
            if key not in value:
                return default
            value = value.get(key, default)
        return value

    def __getitem__(self, item):
        return self.get(item)

    #
    # Main directories for Hop3
    #
    @property
    def HOP3_ROOT(self) -> Path:
        return self._home

    @property
    def HOP3_USER(self) -> str:
        return self._user

    @property
    def HOP3_BIN(self) -> Path:
        return self._home / "bin"

    @property
    def HOP3_SCRIPT(self) -> str:
        return str(self._home / "venv" / "bin" / "hop-agent")

    @property
    def APP_ROOT(self) -> Path:
        return self._home / "apps"

    #
    # NGINX config
    #
    @property
    def NGINX_ROOT(self) -> Path:
        return self._home / "nginx"

    @property
    def CACHE_ROOT(self) -> Path:
        return self._home / "cache"

    #
    # UWSGI config
    #
    @property
    def UWSGI_ROOT(self) -> Path:
        return self._home / "uwsgi"

    @property
    def UWSGI_AVAILABLE(self) -> Path:
        return self._home / "uwsgi-available"

    @property
    def UWSGI_ENABLED(self) -> Path:
        return self._home / "uwsgi-enabled"

    @property
    def UWSGI_LOG_MAXSIZE(self) -> str:
        return "1048576"

    #
    # ACME (letsencrypt) config
    #
    @property
    def ACME_ROOT(self) -> Path:
        if "ACME_ROOT" in os.environ:
            return Path(os.environ["ACME_ROOT"])
        return self._home / ".acme.sh"

    @property
    def ACME_WWW(self) -> Path:
        return self._home / "acme"

    @property
    def ACME_ROOT_CA(self) -> str:
        return self._config.get("acme.root_ca", "letsencrypt.org")

    #
    # Misc
    #
    @property
    def ROOT_DIRS(self) -> list[Path]:
        return [
            self.APP_ROOT,
            self.CACHE_ROOT,
            self.UWSGI_ROOT,
            self.UWSGI_AVAILABLE,
            self.UWSGI_ENABLED,
            self.NGINX_ROOT,
        ]

    @property
    def CRON_REGEXP(self) -> str:
        return (
            r"^((?:(?:\*\/)?\d+)|\*) "
            r"((?:(?:\*\/)?\d+)|\*) "
            r"((?:(?:\*\/)?\d+)|\*) "
            r"((?:(?:\*\/)?\d+)|\*) "
            r"((?:(?:\*\/)?\d+)|\*) "
            r"(.*)$"
        )


# Singleton instance of the Config class
config = Config()
