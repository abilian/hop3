#!/usr/bin/env python3
"""Baserow start script for Hop3."""

import os
import secrets
import subprocess
import sys
from pathlib import Path

# Environment configuration
DATA_DIR = Path(os.environ.get("HOP3_DATA_DIR", "/app/data"))
CODE_DIR = Path(os.environ.get("HOP3_CODE_DIR", "/app/code"))
HOP3_USER = os.environ.get("HOP3_USER", "www-data")

# Database configuration
POSTGRES_USERNAME = os.environ.get("POSTGRES_USERNAME", "baserow")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_DATABASE = os.environ.get("POSTGRES_DATABASE", "baserow")

# Redis configuration
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "")
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")

# Mail configuration
MAIL_FROM = os.environ.get("MAIL_FROM", "noreply@localhost")
SMTP_HOST = os.environ.get("SMTP_HOST", "localhost")
SMTP_PORT = os.environ.get("SMTP_PORT", "25")
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")


def run(cmd: list[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    return subprocess.run(cmd, check=check, **kwargs)


def generate_secret(length: int = 50) -> str:
    """Generate a random secret key."""
    chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(secrets.choice(chars) for _ in range(length))


def main() -> int:
    # Create directories
    (DATA_DIR / "media").mkdir(parents=True, exist_ok=True)
    Path("/run/temp").mkdir(parents=True, exist_ok=True)

    # Generate secret if not exists
    secret_file = DATA_DIR / ".secret"
    if not secret_file.exists():
        secret = generate_secret()
        secret_file.write_text(f"export SECRET_KEY={secret}\n")

    # Source the secret
    secret_content = secret_file.read_text()
    for line in secret_content.strip().split("\n"):
        if line.startswith("export "):
            key, _, value = line[7:].partition("=")
            os.environ[key] = value

    # Create env.sh if not exists
    env_file = DATA_DIR / "env.sh"
    if not env_file.exists():
        env_file.write_text(
            "# Add Baserow customizations here (https://baserow.io/docs/installation/configuration)\n\n"
            "export BASEROW_BACKEND_LOG_LEVEL=INFO\n"
        )

    # Source env.sh
    env_content = env_file.read_text()
    for line in env_content.strip().split("\n"):
        if line.startswith("export "):
            key, _, value = line[7:].partition("=")
            os.environ[key] = value

    # Set environment variables
    app_origin = os.environ.get("HOP3_APP_ORIGIN", "http://localhost")
    os.environ["BASEROW_PUBLIC_URL"] = app_origin
    os.environ["PRIVATE_BACKEND_URL"] = "http://localhost:8000"
    os.environ["DATABASE_URL"] = (
        f"postgresql://{POSTGRES_USERNAME}:{POSTGRES_PASSWORD}@"
        f"{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DATABASE}"
    )
    os.environ["REDIS_URL"] = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}"
    os.environ["MEDIA_ROOT"] = str(DATA_DIR / "media")

    # Email settings
    os.environ["EMAIL_SMTP"] = "true"
    os.environ["EMAIL_SMTP_USE_TLS"] = ""
    os.environ["FROM_EMAIL"] = MAIL_FROM
    os.environ["EMAIL_SMTP_HOST"] = SMTP_HOST
    os.environ["EMAIL_SMTP_PORT"] = SMTP_PORT
    os.environ["EMAIL_SMTP_USER"] = SMTP_USERNAME
    os.environ["EMAIL_SMTP_PASSWORD"] = SMTP_PASSWORD

    os.environ["MIGRATE_ON_STARTUP"] = "false"
    os.environ["BASEROW_TRIGGER_SYNC_TEMPLATES_AFTER_MIGRATION"] = "false"

    # Change ownership
    print("==> Changing ownership")
    run(["chown", "-R", f"{HOP3_USER}:{HOP3_USER}", str(DATA_DIR)])

    # Run database migrations
    print("==> Executing database migrations")
    manage_py = CODE_DIR / "backend" / "src" / "baserow" / "manage.py"
    python_bin = CODE_DIR / "env" / "bin" / "python"
    run(
        [
            "su",
            "-s",
            "/bin/bash",
            HOP3_USER,
            "-c",
            f"{python_bin} {manage_py} migrate",
        ]
    )

    # Sync templates in background
    print("==> Syncing templates (in the background)")
    subprocess.Popen(
        [
            "su",
            "-s",
            "/bin/bash",
            HOP3_USER,
            "-c",
            f"{python_bin} {manage_py} sync_templates",
        ]
    )

    # Start Baserow
    print("==> Starting Baserow")
    os.execvp(
        "/usr/bin/supervisord",
        [
            "/usr/bin/supervisord",
            "--configuration",
            "/etc/supervisor/supervisord.conf",
            "--nodaemon",
            "-i",
            "Baserow",
        ],
    )


if __name__ == "__main__":
    sys.exit(main() or 0)
