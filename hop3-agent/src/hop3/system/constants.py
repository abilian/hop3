# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Globals constants for Hop3."""

from __future__ import annotations

from os import environ
from os.path import abspath, join
from pathlib import Path

# Useful for developing
if "PYTEST_VERSION" in environ:
    # Hack to set up early when testing
    _HOME = "/tmp/hop3"
elif "HOP3_HOME" in environ:
    _HOME = environ["HOP3_HOME"]
else:
    _HOME = environ["HOME"]

_HOP3_HOME = Path(_HOME)
HOP3_USER = environ.get("HOP3_USER", "hop3")

HOP3_BIN = _HOP3_HOME / "bin"
HOP3_SCRIPT = str(_HOP3_HOME / "venv" / "bin" / "hop-agent")

# Main directories for Hop3
HOP3_ROOT = _HOP3_HOME.resolve()
APP_ROOT = HOP3_ROOT / "apps"
DATA_ROOT = HOP3_ROOT / "data"
ENV_ROOT = HOP3_ROOT / "envs"
GIT_ROOT = HOP3_ROOT / "repos"
LOG_ROOT = HOP3_ROOT / "logs"
NGINX_ROOT = HOP3_ROOT / "nginx"
CACHE_ROOT = HOP3_ROOT / "cache"

UWSGI_AVAILABLE = HOP3_ROOT / "uwsgi-available"
UWSGI_ENABLED = HOP3_ROOT / "uwsgi-enabled"
UWSGI_ROOT = HOP3_ROOT / "uwsgi"
UWSGI_LOG_MAXSIZE = "1048576"

ACME_ROOT = environ.get("ACME_ROOT", join(environ["HOME"], ".acme.sh"))
ACME_WWW = abspath(join(HOP3_ROOT, "acme"))
ACME_ROOT_CA = environ.get("ACME_ROOT_CA", "letsencrypt.org")

ROOT_DIRS: list[Path] = [
    APP_ROOT,
    CACHE_ROOT,
    DATA_ROOT,
    GIT_ROOT,
    ENV_ROOT,
    UWSGI_ROOT,
    UWSGI_AVAILABLE,
    UWSGI_ENABLED,
    LOG_ROOT,
    NGINX_ROOT,
]

CRON_REGEXP = (
    r"^((?:(?:\*\/)?\d+)|\*) "
    r"((?:(?:\*\/)?\d+)|\*) "
    r"((?:(?:\*\/)?\d+)|\*) "
    r"((?:(?:\*\/)?\d+)|\*) "
    r"((?:(?:\*\/)?\d+)|\*) "
    r"(.*)$"
)
