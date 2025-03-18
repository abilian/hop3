# Copyright (c) 2024, Abilian SAS
from __future__ import annotations

import os
import re
from pathlib import Path

from hop3.lib.config import Config

config = Config()

TESTING = "PYTEST_VERSION" in os.environ

if TESTING:
    os.environ["HOP3_ROOT"] = "/tmp/hop3"


def get_parameters():
    return {k: v for k, v in globals().items() if re.match("[A-Z0-9_]+$", k)}


HOP3_ROOT: Path = config.get("HOP3_ROOT", Path, "/home/hop3")
HOP3_USER: str = config.get("HOP3_USER", str, "hop3")

HOP3_BIN: Path = HOP3_ROOT / "bin"
HOP3_SCRIPT: str = str(HOP3_ROOT / "venv" / "bin" / "hop-agent")

APP_ROOT: Path = HOP3_ROOT / "apps"

NGINX_ROOT: Path = HOP3_ROOT / "nginx"
CACHE_ROOT: Path = HOP3_ROOT / "cache"

UWSGI_ROOT: Path = HOP3_ROOT / "uwsgi"
UWSGI_AVAILABLE: Path = HOP3_ROOT / "uwsgi-available"
UWSGI_ENABLED: Path = HOP3_ROOT / "uwsgi-enabled"
UWSGI_LOG_MAXSIZE: str = "1048576"

ACME_ROOT: Path = HOP3_ROOT / ".acme.sh"
ACME_WWW: Path = HOP3_ROOT / "acme"
ACME_ROOT_CA: str = config.get("acme.root_ca", default="letsencrypt.org")

ROOT_DIRS = [
    APP_ROOT,
    CACHE_ROOT,
    UWSGI_ROOT,
    UWSGI_AVAILABLE,
    UWSGI_ENABLED,
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
