#!/usr/bin/env python3
"""Penpot start script for Hop3."""

import os
import secrets
import subprocess
import sys
from pathlib import Path

# Environment configuration
DATA_DIR = Path(os.environ.get("HOP3_DATA_DIR", "/app/data"))
HOP3_USER = os.environ.get("HOP3_USER", "www-data")

# App configuration
HOP3_APP_ORIGIN = os.environ.get("HOP3_APP_ORIGIN", "http://localhost")

# Database configuration
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_DATABASE = os.environ.get("POSTGRES_DATABASE", "penpot")
POSTGRES_USERNAME = os.environ.get("POSTGRES_USERNAME", "penpot")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")

# Redis configuration
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")

# OIDC configuration
OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "")
OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "")

# Mail configuration
MAIL_FROM_DISPLAY_NAME = os.environ.get("MAIL_FROM_DISPLAY_NAME", "Penpot")
MAIL_FROM = os.environ.get("MAIL_FROM", "noreply@localhost")
SMTP_HOST = os.environ.get("SMTP_HOST", "localhost")
SMTP_PORT = os.environ.get("SMTP_PORT", "25")
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")


def run(cmd: list[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    return subprocess.run(cmd, check=check, **kwargs)


def generate_password(length: int = 32) -> str:
    """Generate a random password."""
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def main() -> int:
    # Create directories
    Path("/run/penpot").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "assets").mkdir(parents=True, exist_ok=True)

    # Feature flags
    PENPOT_BACKEND_FLAGS = "disable-onboarding enable-registration disable-login-with-password disable-email-verification enable-smtp enable-login-with-oidc"
    PENPOT_FRONTEND_FLAGS = "disable-onboarding disable-registration disable-login-with-password disable-email-verification enable-smtp enable-login-with-oidc"

    os.environ["PENPOT_BACKEND_FLAGS"] = PENPOT_BACKEND_FLAGS
    os.environ["PENPOT_FRONTEND_FLAGS"] = PENPOT_FRONTEND_FLAGS

    # Generate secret key if not exists
    secret_file = DATA_DIR / ".secret_key"
    if not secret_file.exists():
        secret_file.write_text(generate_password(32))

    os.environ["NODE_ENV"] = "production"

    # Read secret key
    secret_key = secret_file.read_text().strip()

    # Create environment script
    env_content = f"""## You can read more about all available flags and other
## environment variables for the backend here:
## https://help.penpot.app/technical-guide/configuration/#advanced-configuration
export PENPOT_FLAGS="{PENPOT_BACKEND_FLAGS}"

export PENPOT_PUBLIC_URI={HOP3_APP_ORIGIN}
export PENPOT_REDIS_URI="redis://{REDIS_HOST}/0"

export PENPOT_SECRET_KEY={secret_key}

export PENPOT_DATABASE_URI="postgresql://{POSTGRES_HOST}/{POSTGRES_DATABASE}"
export PENPOT_DATABASE_USERNAME={POSTGRES_USERNAME}
export PENPOT_DATABASE_PASSWORD={POSTGRES_PASSWORD}

export PENPOT_ASSETS_STORAGE_BACKEND=assets-fs
export PENPOT_STORAGE_ASSETS_FS_DIRECTORY={DATA_DIR}/assets

# OIDC
export PENPOT_OIDC_BASE_URI="{OIDC_ISSUER}"
export PENPOT_OIDC_CLIENT_ID="{OIDC_CLIENT_ID}"
export PENPOT_OIDC_CLIENT_SECRET="{OIDC_CLIENT_SECRET}"
export PENPOT_OIDC_SCOPES="openid profile email"

# SMTP/Email configuration.
export PENPOT_SMTP_DEFAULT_FROM="{MAIL_FROM_DISPLAY_NAME} <{MAIL_FROM}>"
export PENPOT_SMTP_DEFAULT_REPLY_TO="{MAIL_FROM_DISPLAY_NAME} <{MAIL_FROM}>"
export PENPOT_SMTP_HOST={SMTP_HOST}
export PENPOT_SMTP_PORT={SMTP_PORT}
export PENPOT_SMTP_USERNAME={SMTP_USERNAME}
export PENPOT_SMTP_PASSWORD={SMTP_PASSWORD}
export PENPOT_SMTP_TLS=false
export PENPOT_SMTP_SSL=false

"""
    Path("/run/penpot/env.sh").write_text(env_content)

    # Source the env file (set environment variables)
    for line in env_content.split("\n"):
        if line.startswith("export "):
            # Extract key=value
            kv = line[7:]  # Remove "export "
            if "=" in kv:
                key, _, value = kv.partition("=")
                # Remove quotes if present
                value = value.strip('"')
                os.environ[key] = value

    # Create frontend config
    frontend_config = f'var penpotFlags = "{PENPOT_FRONTEND_FLAGS}";\n'
    Path("/run/config.js").write_text(frontend_config)

    # Ensure permissions
    print("=> Ensure permissions")
    Path("/run/penpot/env.sh").chmod(0o755)
    run(["chown", "-R", f"{HOP3_USER}:{HOP3_USER}", str(DATA_DIR), "/run/penpot"])

    # Start supervisor
    print("=> Starting supervisor")
    os.execvp(
        "/usr/bin/supervisord",
        [
            "/usr/bin/supervisord",
            "--configuration",
            "/etc/supervisor/supervisord.conf",
            "--nodaemon",
            "-i",
            "Penpot",
        ],
    )


if __name__ == "__main__":
    sys.exit(main() or 0)
