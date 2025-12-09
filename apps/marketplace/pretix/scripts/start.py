#!/usr/bin/env python3
"""Pretix start script for Hop3."""

import configparser
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Environment configuration
DATA_DIR = Path(os.environ.get("HOP3_DATA_DIR", "/app/data"))
CODE_DIR = Path(os.environ.get("HOP3_CODE_DIR", "/app/code"))
PKG_DIR = Path(os.environ.get("HOP3_PKG_DIR", "/app/pkg"))
HOP3_USER = os.environ.get("HOP3_USER", "www-data")
VENV_PATH = Path(os.environ.get("VENV_PATH", "/app/code/venv"))

# App configuration
HOP3_APP_ORIGIN = os.environ.get("HOP3_APP_ORIGIN", "http://localhost")
HOP3_APP_DOMAIN = os.environ.get("HOP3_APP_DOMAIN", "localhost")

# Database configuration
POSTGRES_DATABASE = os.environ.get("POSTGRES_DATABASE", "pretix")
POSTGRES_USERNAME = os.environ.get("POSTGRES_USERNAME", "pretix")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")

# Redis configuration
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "")
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")

# Mail configuration
SMTP_HOST = os.environ.get("SMTP_HOST", "localhost")
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_PORT = os.environ.get("SMTP_PORT", "25")
MAIL_FROM = os.environ.get("MAIL_FROM", "noreply@localhost")

# OIDC configuration
OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "")
OIDC_PROVIDER_NAME = os.environ.get("OIDC_PROVIDER_NAME", "SSO")
OIDC_AUTH_ENDPOINT = os.environ.get("OIDC_AUTH_ENDPOINT", "")
OIDC_TOKEN_ENDPOINT = os.environ.get("OIDC_TOKEN_ENDPOINT", "")
OIDC_PROFILE_ENDPOINT = os.environ.get("OIDC_PROFILE_ENDPOINT", "")
OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "")


def run(cmd: list[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    return subprocess.run(cmd, check=check, **kwargs)


def crudini_set(file_path: str, section: str, key: str, value: str):
    """Set a value in an INI file (similar to crudini --set)."""
    config = configparser.ConfigParser()
    config.read(file_path)

    if not config.has_section(section):
        config.add_section(section)

    config.set(section, key, value)

    with open(file_path, "w") as f:
        config.write(f)


def main() -> int:
    print("=> Starting Pretix")

    print("=> Creating directories")
    (DATA_DIR / "data" / "media").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "site-packages").mkdir(parents=True, exist_ok=True)
    Path("/run/pretix").mkdir(parents=True, exist_ok=True)

    # Set environment for pretix config
    os.environ["PRETIX_CONFIG_FILE"] = "/run/pretix/pretix.cfg"

    print("=> Generating nginx.conf")
    nginx_template = PKG_DIR / "nginx.conf"
    if nginx_template.exists():
        content = nginx_template.read_text()
        content = content.replace("##HOSTNAME##", HOP3_APP_DOMAIN)
        Path("/run/nginx.conf").write_text(content)

    # Create default config if not exists
    config_file = DATA_DIR / "config.cfg"
    if not config_file.exists():
        config_file.write_text(
            """# Add custom Pretix configuration in this file
# https://docs.pretix.eu/self-hosting/config/#pretix-settings

[pretix]
instance_name=My pretix installation
currency=EUR
"""
        )

    # Copy user config to runtime config
    pretix_cfg = Path("/run/pretix/pretix.cfg")
    shutil.copy(config_file, pretix_cfg)

    # Update configuration using crudini-like operations
    crudini_set(str(pretix_cfg), "pretix", "url", HOP3_APP_ORIGIN)
    crudini_set(str(pretix_cfg), "pretix", "trust_x_forwarded_for", "on")
    crudini_set(str(pretix_cfg), "pretix", "trust_x_forwarded_proto", "on")

    # Database
    crudini_set(str(pretix_cfg), "database", "backend", "postgresql")
    crudini_set(str(pretix_cfg), "database", "name", POSTGRES_DATABASE)
    crudini_set(str(pretix_cfg), "database", "user", POSTGRES_USERNAME)
    crudini_set(str(pretix_cfg), "database", "password", POSTGRES_PASSWORD)
    crudini_set(str(pretix_cfg), "database", "host", POSTGRES_HOST)
    crudini_set(str(pretix_cfg), "database", "port", POSTGRES_PORT)

    # SMTP
    crudini_set(str(pretix_cfg), "mail", "host", SMTP_HOST)
    crudini_set(str(pretix_cfg), "mail", "user", SMTP_USERNAME)
    crudini_set(str(pretix_cfg), "mail", "password", SMTP_PASSWORD)
    crudini_set(str(pretix_cfg), "mail", "port", SMTP_PORT)
    crudini_set(str(pretix_cfg), "mail", "tls", "off")
    crudini_set(str(pretix_cfg), "mail", "ssl", "off")
    crudini_set(str(pretix_cfg), "mail", "from", MAIL_FROM)
    crudini_set(str(pretix_cfg), "mail", "custom_smtp_allow_private_networks", "True")

    # Redis
    redis_url = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}/0"
    crudini_set(str(pretix_cfg), "redis", "location", redis_url)

    # Celery
    crudini_set(str(pretix_cfg), "celery", "backend", f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}/1")
    crudini_set(str(pretix_cfg), "celery", "broker", f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}/2")

    # OIDC
    if OIDC_ISSUER:
        print("=> Configure OIDC")
        crudini_set(
            str(pretix_cfg),
            "pretix",
            "auth_backends",
            "pretix.base.auth.NativeAuthBackend,pretix_oidc.auth.OIDCAuthBackend",
        )
        crudini_set(str(pretix_cfg), "oidc", "title", f"Login with {OIDC_PROVIDER_NAME}")
        crudini_set(str(pretix_cfg), "oidc", "issuer", OIDC_ISSUER)
        crudini_set(str(pretix_cfg), "oidc", "authorization_endpoint", OIDC_AUTH_ENDPOINT)
        crudini_set(str(pretix_cfg), "oidc", "token_endpoint", OIDC_TOKEN_ENDPOINT)
        crudini_set(str(pretix_cfg), "oidc", "userinfo_endpoint", OIDC_PROFILE_ENDPOINT)
        crudini_set(str(pretix_cfg), "oidc", "end_session_endpoint", "")
        crudini_set(str(pretix_cfg), "oidc", "jwks_uri", f"{OIDC_ISSUER}/jwks")
        crudini_set(str(pretix_cfg), "oidc", "client_id", OIDC_CLIENT_ID)
        crudini_set(str(pretix_cfg), "oidc", "client_secret", OIDC_CLIENT_SECRET)
        crudini_set(str(pretix_cfg), "oidc", "scopes", "openid,email,profile")
        crudini_set(str(pretix_cfg), "oidc", "unique_attribute", "sub")
    else:
        crudini_set(
            str(pretix_cfg), "pretix", "auth_backends", "pretix.base.auth.NativeAuthBackend"
        )

    # Run database migration
    print("=> Run database migration")
    run(["python", "-m", "pretix", "migrate"])
    run(["python", "-m", "pretix", "rebuild"])

    # Change permissions
    print("=> Changing permissions")
    run(["chown", "-R", f"{HOP3_USER}:{HOP3_USER}", str(DATA_DIR), "/run/pretix"])

    # Run cron script in background
    cron_script = Path("/app/scripts/cron.sh")
    if cron_script.exists():
        subprocess.Popen([str(cron_script)])

    # Start Pretix
    print("=> Starting Pretix")
    os.execvp(
        "/usr/bin/supervisord",
        [
            "/usr/bin/supervisord",
            "--configuration",
            "/etc/supervisor/supervisord.conf",
            "--nodaemon",
            "-i",
            "Pretix",
        ],
    )


if __name__ == "__main__":
    sys.exit(main() or 0)
