#!/usr/bin/env python3
"""Redash start script for Hop3."""

import os
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path

# Environment configuration
DATA_DIR = Path(os.environ.get("HOP3_DATA_DIR", "/app/data"))
CODE_DIR = Path(os.environ.get("HOP3_CODE_DIR", "/app/code"))
HOP3_USER = os.environ.get("HOP3_USER", "www-data")

# App configuration
HOP3_APP_ORIGIN = os.environ.get("HOP3_APP_ORIGIN", "http://localhost:5000")

# Database configuration
POSTGRES_USERNAME = os.environ.get("POSTGRES_USERNAME", "redash")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_DATABASE = os.environ.get("POSTGRES_DATABASE", "redash")

# Redis configuration
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = os.environ.get("REDIS_PORT", "6379")

# Mail configuration
SMTP_HOST = os.environ.get("SMTP_HOST", "localhost")
SMTP_PORT = os.environ.get("SMTP_PORT", "25")
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
MAIL_FROM = os.environ.get("MAIL_FROM", "noreply@localhost")

# LDAP configuration
LDAP_URL = os.environ.get("LDAP_URL", "")
LDAP_BIND_DN = os.environ.get("LDAP_BIND_DN", "")
LDAP_BIND_PASSWORD = os.environ.get("LDAP_BIND_PASSWORD", "")
LDAP_USERS_BASE_DN = os.environ.get("LDAP_USERS_BASE_DN", "")


def run(cmd: list[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    return subprocess.run(cmd, check=check, **kwargs)


def setup_admin():
    """Setup admin user after server starts."""
    # Wait for app to come up
    while True:
        try:
            result = run(
                ["curl", "--fail", "http://localhost:5000"],
                check=False,
                capture_output=True,
            )
            if result.returncode == 0:
                break
        except Exception:
            pass
        print("Waiting for redash to come up")
        time.sleep(1)

    # Create admin user
    run(
        [
            "curl",
            "http://localhost:5000/setup",
            "-H",
            "Content-Type: application/x-www-form-urlencoded",
            "--data",
            "name=Administrator&email=admin%40localhost&password=changeme&org_name=MyOrg",
        ],
        check=False,
    )

    print("Administrator setup")


def main() -> int:
    # Create directories
    Path("/run/redash").mkdir(parents=True, exist_ok=True)
    Path("/run/snowflake-home").mkdir(parents=True, exist_ok=True)

    # Migration: rename env to env.sh
    old_env = DATA_DIR / "env"
    new_env = DATA_DIR / "env.sh"
    if old_env.exists() and not new_env.exists():
        old_env.rename(new_env)

    # Generate initial env file if not exists
    if not new_env.exists():
        print("==> Generating initial secrets")
        cookie_secret = secrets.token_hex(32)
        secret_key = secrets.token_hex(32)
        new_env.write_text(
            f"# See env vars at https://redash.io/help/open-source/admin-guide/env-vars-settings/\n"
            f"export REDASH_COOKIE_SECRET={cookie_secret}\n"
            f"export REDASH_SECRET_KEY={secret_key}\n"
            f"export REDASH_WEB_WORKERS=4\n"
        )

    # Set environment variables
    print("==> Creating environment configs")

    os.environ["REDASH_HOST"] = HOP3_APP_ORIGIN
    os.environ["REDASH_LOG_LEVEL"] = "INFO"
    os.environ["REDASH_REDIS_URL"] = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"
    os.environ["REDASH_DATABASE_URL"] = (
        f"postgresql://{POSTGRES_USERNAME}:{POSTGRES_PASSWORD}@"
        f"{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DATABASE}"
    )

    # Mail configuration
    os.environ["REDASH_MAIL_SERVER"] = SMTP_HOST
    os.environ["REDASH_MAIL_PORT"] = SMTP_PORT
    os.environ["REDASH_MAIL_USE_TLS"] = "false"
    os.environ["REDASH_MAIL_USE_SSL"] = "false"
    os.environ["REDASH_MAIL_USERNAME"] = SMTP_USERNAME
    os.environ["REDASH_MAIL_PASSWORD"] = SMTP_PASSWORD
    os.environ["REDASH_MAIL_DEFAULT_SENDER"] = MAIL_FROM

    # LDAP configuration
    if LDAP_URL:
        os.environ["REDASH_LDAP_LOGIN_ENABLED"] = "true"
        os.environ["REDASH_PASSWORD_LOGIN_ENABLED"] = "true"
        os.environ["REDASH_LDAP_URL"] = LDAP_URL
        os.environ["REDASH_LDAP_BIND_DN"] = LDAP_BIND_DN
        os.environ["REDASH_LDAP_BIND_DN_PASSWORD"] = LDAP_BIND_PASSWORD
        os.environ["REDASH_LDAP_CUSTOM_USERNAME_PROMPT"] = "Username"
        os.environ["REDASH_SEARCH_DN"] = LDAP_USERS_BASE_DN
        os.environ["REDASH_LDAP_SEARCH_TEMPLATE"] = "(|(mail=%(username)s)(username=%(username)s))"
        os.environ["REDASH_LDAP_EMAIL_KEY"] = "mail"
        os.environ["REDASH_LDAP_DISPLAY_NAME_KEY"] = "displayName"

    os.environ["REDASH_WEB_WORKERS"] = "4"
    os.environ["REDASH_VERSION_CHECK"] = "false"

    # Source env.sh
    env_content = new_env.read_text()
    for line in env_content.strip().split("\n"):
        if line.startswith("export "):
            kv = line[7:]
            if "=" in kv:
                key, _, value = kv.partition("=")
                os.environ[key] = value

    # Database setup or migration
    setup_file = DATA_DIR / ".setup"
    manage_py = CODE_DIR / "redash" / "manage.py"

    if not setup_file.exists():
        print("==> First run. Creating tables")
        run(["python", str(manage_py), "database", "create_tables"])
        setup_file.touch()
    else:
        print("==> Upgrading redash")
        run(["python", str(manage_py), "db", "upgrade"])

    # Change ownership
    run(["chown", "-R", f"{HOP3_USER}:{HOP3_USER}", "/run/redash", str(DATA_DIR)])

    # Check if org exists, if not setup admin in background
    result = run(
        ["python", str(manage_py), "org", "list"],
        check=False,
        capture_output=True,
        text=True,
    )
    if not result.stdout.strip():
        print("==> Setting up administrator")
        t = threading.Thread(target=setup_admin)
        t.daemon = True
        t.start()

    # Set additional env vars
    os.environ["WORKERS_COUNT"] = "4"
    os.environ["HOP3_USER"] = HOP3_USER

    # Start redash
    print("==> Starting redash")
    os.execvp(
        "/usr/bin/supervisord",
        [
            "/usr/bin/supervisord",
            "--configuration",
            "/etc/supervisor/supervisord.conf",
            "--nodaemon",
            "-i",
            "Redash",
        ],
    )


if __name__ == "__main__":
    sys.exit(main() or 0)
