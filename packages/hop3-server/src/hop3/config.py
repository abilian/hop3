# Copyright (c) 2024-2025, Abilian SAS
from __future__ import annotations

import os
import re
from pathlib import Path

from hop3.lib.config import Config

# Load server configuration from hop3-server.toml if it exists
TESTING = "PYTEST_VERSION" in os.environ

if not TESTING:
    # Try to load from the standard location
    hop3_root = Path(os.environ.get("HOP3_ROOT", "/home/hop3"))
    config_file = hop3_root / "hop3-server.toml"
    if config_file.exists():
        config = Config(file=config_file)
    else:
        config = Config()
else:
    config = Config()

if TESTING:
    os.environ["HOP3_ROOT"] = "/tmp/hop3"
    os.environ["ACME_ENGINE"] = "self-signed"
    os.environ["ACME_EMAIL"] = "test@example.com"


def get_parameters():
    return {k: v for k, v in globals().items() if re.match(r"[A-Z0-9_]+$", k)}


# Configured
MODE = config.get_str("MODE", "production")

HOP3_ROOT = config.get_path("HOP3_ROOT", "/home/hop3")
HOP3_USER = config.get_str("HOP3_USER", "hop3")

ACME_ENGINE = config.get_str("ACME_ENGINE", "certbot")
ACME_ROOT_CA = config.get_str("ACME_ROOT_CA", "letsencrypt.org")
# FIXME
ACME_EMAIL = config.get_str("ACME_EMAIL", "fixme@example.com")

HOP3_DEBUG = config.get_bool("HOP3_DEBUG", False)

# Security
HOP3_SECRET_KEY = config.get_str("HOP3_SECRET_KEY", "")
HOP3_TOKEN_EXPIRY_HOURS = config.get_int("HOP3_TOKEN_EXPIRY_HOURS", 24)
# UNSAFE MODE: Disables all authentication - USE ONLY FOR TESTING
HOP3_UNSAFE = config.get_bool("HOP3_UNSAFE", False)

# Proxy configuration (server-wide)
HOP3_PROXY_TYPE = config.get_str("HOP3_PROXY_TYPE", "nginx")

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
