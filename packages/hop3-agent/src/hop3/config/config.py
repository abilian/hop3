# Copyright (c) 2024, Abilian SAS
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import toml


@dataclass
class Config:
    _home: Path = Path("/home/hop3")
    _user: str = "hop3"
    _config: dict[str, Any] = field(default_factory=dict)

    def set_home(self, home: Path):
        self._home = home

    def read_toml(self, path: Path):
        self._config = toml.load(path)

    def __getattr__(self, item):
        key = item.upper()
        if hasattr(self, key):
            return getattr(self, key)
        msg = f"Config has no attribute {item}"
        raise AttributeError(msg)

    @property
    def hop3_home(self) -> Path:
        return self._home

    @property
    def hop3_user(self) -> str:
        return self._config["user"]

    @property
    def hop3_bin(self) -> Path:
        return self._home / "bin"

    @property
    def hop3_script(self) -> str:
        return str(self._home / "venv" / "bin" / "hop-agent")

    @property
    def app_root(self) -> Path:
        return self._home / "apps"

    @property
    def nginx_root(self) -> Path:
        return self._home / "nginx"

    @property
    def cache_root(self) -> Path:
        return self._home / "cache"

    @property
    def uwsgi_available(self) -> Path:
        return self._home / "uwsgi-available"

    @property
    def uwsgi_enabled(self) -> Path:
        return self._home / "uwsgi-enabled"

    @property
    def uwsgi_root(self) -> Path:
        return self._home / "uwsgi"

    @property
    def uwsgi_log_maxsize(self) -> str:
        return "1048576"

    @property
    def acme_root(self) -> str:
        return self._config.get("acme_root", "/home/hop3/.acme.sh")

    @property
    def acme_www(self) -> str:
        return str(self._home / "acme")

    @property
    def acme_root_ca(self) -> str:
        return self._config.get("acme_root_ca", "letsencrypt.org")

    @property
    def root_dirs(self) -> list[Path]:
        return [
            self.app_root,
            self.cache_root,
            self.uwsgi_root,
            self.uwsgi_available,
            self.uwsgi_enabled,
            self.nginx_root,
        ]

    @property
    def cron_regexp(self) -> str:
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

# # Useful for developing
# HOP3_TESTING = "PYTEST_VERSION" in environ
#
# if HOP3_TESTING:
#     # Hack to set up early when testing
#     _HOME = "/tmp/hop3"
# elif "HOP3_HOME" in environ:
#     _HOME = environ["HOP3_HOME"]
# else:
#     _HOME = environ["HOME"]
#
# _HOP3_HOME = Path(_HOME)
# HOP3_USER = environ.get("HOP3_USER", "hop3")
#
# HOP3_BIN = _HOP3_HOME / "bin"
# HOP3_SCRIPT = str(_HOP3_HOME / "venv" / "bin" / "hop-agent")
#
# # Main directories for Hop3
# HOP3_ROOT = _HOP3_HOME.resolve()
# APP_ROOT = HOP3_ROOT / "apps"
# NGINX_ROOT = HOP3_ROOT / "nginx"
# CACHE_ROOT = HOP3_ROOT / "cache"
#
# UWSGI_AVAILABLE = HOP3_ROOT / "uwsgi-available"
# UWSGI_ENABLED = HOP3_ROOT / "uwsgi-enabled"
# UWSGI_ROOT = HOP3_ROOT / "uwsgi"
# UWSGI_LOG_MAXSIZE = "1048576"
#
# ACME_ROOT = environ.get("ACME_ROOT", join(environ["HOME"], ".acme.sh"))
# ACME_WWW = abspath(join(HOP3_ROOT, "acme"))
# ACME_ROOT_CA = environ.get("ACME_ROOT_CA", "letsencrypt.org")
#
# ROOT_DIRS: list[Path] = [
#     APP_ROOT,
#     CACHE_ROOT,
#     UWSGI_ROOT,
#     UWSGI_AVAILABLE,
#     UWSGI_ENABLED,
#     NGINX_ROOT,
# ]
#
# CRON_REGEXP = (
#     r"^((?:(?:\*\/)?\d+)|\*) "
#     r"((?:(?:\*\/)?\d+)|\*) "
#     r"((?:(?:\*\/)?\d+)|\*) "
#     r"((?:(?:\*\/)?\d+)|\*) "
#     r"((?:(?:\*\/)?\d+)|\*) "
#     r"(.*)$"
# )
