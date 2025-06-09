# Copyright (c) 2024-2025, Abilian SAS
from __future__ import annotations

import os
import re

from hop3.lib.config import Config

config = Config()

TESTING = "PYTEST_VERSION" in os.environ

if TESTING:
    os.environ["HOP3_ROOT"] = "/tmp/hop3"
    os.environ["ACME_ENGINE"] = "self-signed"
    os.environ["ACME_EMAIL"] = "test@example.com"


def get_parameters():
    return {k: v for k, v in globals().items() if re.match("[A-Z0-9_]+$", k)}


# Configured
MODE = config.get_str("MODE", "production")

HOP3_ROOT = config.get_path("HOP3_ROOT", "/home/hop3")
HOP3_USER = config.get_str("HOP3_USER", "hop3")

ACME_ENGINE = config.get_str("ACME_ENGINE", "certbot")
ACME_ROOT_CA = config.get_str("ACME_ROOT_CA", "letsencrypt.org")
# FIXME
ACME_EMAIL = config.get_str("ACME_EMAIL", "fixme@example.com")

HOP3_DEBUG = config.get_bool("HOP3_DEBUG", False)

# Computed paths
HOP3_BIN = HOP3_ROOT / "bin"
HOP3_SCRIPT = str(HOP3_ROOT / "venv" / "bin" / "hop-agent")

APP_ROOT = HOP3_ROOT / "apps"

NGINX_ROOT = HOP3_ROOT / "nginx"
CACHE_ROOT = HOP3_ROOT / "cache"
CADDY_ROOT = HOP3_ROOT / "caddy"
TRAEFIK_ROOT = HOP3_ROOT / "traefik"

UWSGI_ROOT = HOP3_ROOT / "uwsgi"
UWSGI_AVAILABLE = HOP3_ROOT / "uwsgi-available"
UWSGI_ENABLED = HOP3_ROOT / "uwsgi-enabled"
UWSGI_LOG_MAXSIZE = "1048576"

ACME_WWW = HOP3_ROOT / "acme"

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
