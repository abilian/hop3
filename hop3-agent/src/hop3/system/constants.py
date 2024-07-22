# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

"""Globals constants for Hop3."""

from __future__ import annotations

from os import environ
from os.path import abspath, join
from pathlib import Path

HOME = environ["HOME"]

HOP3_HOME = HOME
HOP3_BIN = join(HOP3_HOME, "bin")
HOP3_SCRIPT = str(Path(HOP3_HOME, "venv", "bin", "hop-agent"))

# Main directories for Hop3
HOP3_ROOT = HOP3_HOME
APP_ROOT = abspath(join(HOP3_ROOT, "apps"))
DATA_ROOT = abspath(join(HOP3_ROOT, "data"))
ENV_ROOT = abspath(join(HOP3_ROOT, "envs"))
GIT_ROOT = abspath(join(HOP3_ROOT, "repos"))
LOG_ROOT = abspath(join(HOP3_ROOT, "logs"))
NGINX_ROOT = abspath(join(HOP3_ROOT, "nginx"))
CACHE_ROOT = abspath(join(HOP3_ROOT, "cache"))

UWSGI_AVAILABLE = Path(HOP3_ROOT, "uwsgi-available")
UWSGI_ENABLED = Path(HOP3_ROOT, "uwsgi-enabled")
UWSGI_ROOT = abspath(join(HOP3_ROOT, "uwsgi"))
UWSGI_LOG_MAXSIZE = "1048576"

ACME_ROOT = environ.get("ACME_ROOT", join(environ["HOME"], ".acme.sh"))
ACME_WWW = abspath(join(HOP3_ROOT, "acme"))
ACME_ROOT_CA = environ.get("ACME_ROOT_CA", "letsencrypt.org")

ROOT_DIRS: list[str | Path] = [
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
