#!/usr/bin/env python3
"""Weblate start script for Hop3."""

import os
import subprocess
import sys
from pathlib import Path

# Environment configuration
DATA_DIR = Path(os.environ.get("HOP3_DATA_DIR", "/app/data"))
CODE_DIR = Path(os.environ.get("HOP3_CODE_DIR", "/app/code"))
HOP3_USER = os.environ.get("HOP3_USER", "www-data")

# App configuration
HOP3_APP_DOMAIN = os.environ.get("HOP3_APP_DOMAIN", "localhost")

# Database configuration
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_DATABASE = os.environ.get("POSTGRES_DATABASE", "weblate")
POSTGRES_USERNAME = os.environ.get("POSTGRES_USERNAME", "weblate")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")

# Redis configuration
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = os.environ.get("REDIS_PORT", "6379")
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "")

# Mail configuration
SMTP_HOST = os.environ.get("SMTP_HOST", "localhost")
SMTP_PORT = os.environ.get("SMTP_PORT", "25")
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
MAIL_FROM = os.environ.get("MAIL_FROM", "noreply@localhost")

# OIDC configuration
OIDC_PROVIDER_NAME = os.environ.get("OIDC_PROVIDER_NAME", "")


def run(cmd: list[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    return subprocess.run(cmd, check=check, **kwargs)


def main() -> int:
    os.chdir(CODE_DIR)

    print("=> Ensure directories")
    Path("/run/weblate").mkdir(parents=True, exist_ok=True)
    Path("/run/nginx").mkdir(parents=True, exist_ok=True)
    Path("/run/gunicorn/app/weblate").mkdir(parents=True, exist_ok=True)

    # Activate virtual environment
    venv_bin = CODE_DIR / "venv" / "bin"
    os.environ["PATH"] = f"{venv_bin}:{os.environ.get('PATH', '')}"
    os.environ["VIRTUAL_ENV"] = str(CODE_DIR / "venv")

    print("=> Generating nginx.conf")
    nginx_template = (CODE_DIR / "weblate.nginx").read_text()
    nginx_config = nginx_template.replace("##HOSTNAME##", HOP3_APP_DOMAIN)
    Path("/run/nginx.conf").write_text(nginx_config)

    print("=> Get secret key")
    secret_file = DATA_DIR / ".secret_key"
    if not secret_file.exists():
        result = run(
            ["weblate-generate-secret-key"], capture_output=True, text=True
        )
        secret_file.write_text(result.stdout.strip())

    secret_key = secret_file.read_text().strip()
    os.environ["SECRET_KEY"] = secret_key

    # Set OIDC provider name
    if not OIDC_PROVIDER_NAME:
        os.environ["OIDC_PROVIDER_NAME"] = "SSO"
    else:
        os.environ["OIDC_PROVIDER_NAME"] = OIDC_PROVIDER_NAME

    print("=> Ensure custom_settings")
    custom_settings = DATA_DIR / "custom_settings.py"
    if not custom_settings.exists():
        custom_settings.write_text(
            "# Add custom settings here to override the defaults\n"
            "# https://docs.weblate.org/en/latest/admin/config.html\n\n"
        )

    # Database configuration
    os.environ["WEBLATE_DATABASE_HOST"] = POSTGRES_HOST
    os.environ["WEBLATE_DATABASE_PORT"] = POSTGRES_PORT
    os.environ["WEBLATE_DATABASE_NAME"] = POSTGRES_DATABASE
    os.environ["WEBLATE_DATABASE_USER"] = POSTGRES_USERNAME
    os.environ["WEBLATE_DATABASE_PASSWORD"] = POSTGRES_PASSWORD

    # Redis configuration
    os.environ["WEBLATE_REDIS_HOST"] = REDIS_HOST
    os.environ["WEBLATE_REDIS_PORT"] = REDIS_PORT
    os.environ["WEBLATE_REDIS_PASSWORD"] = REDIS_PASSWORD

    # Email configuration
    os.environ["WEBLATE_EMAIL_HOST"] = SMTP_HOST
    os.environ["WEBLATE_EMAIL_PORT"] = SMTP_PORT
    os.environ["WEBLATE_EMAIL_HOST_USER"] = SMTP_USERNAME
    os.environ["WEBLATE_EMAIL_HOST_PASSWORD"] = SMTP_PASSWORD
    os.environ["WEBLATE_DEFAULT_FROM_EMAIL"] = MAIL_FROM

    # Site URL
    os.environ["WEBLATE_SITE_DOMAIN"] = HOP3_APP_DOMAIN
    os.environ["WEBLATE_ENABLE_HTTPS"] = "true"

    print("=> Run migration")
    run(["weblate", "migrate"])

    admin_created = DATA_DIR / ".admin_created"
    if not admin_created.exists():
        print("=> Ensure admin")
        run(
            [
                "weblate",
                "createadmin",
                "--password",
                "changeme123",
                "--username",
                "admin",
                "--email",
                "admin@cloudron.local",
            ]
        )
        admin_created.touch()

    print("=> Ensure permissions")
    run(
        [
            "chown",
            "-R",
            f"{HOP3_USER}:{HOP3_USER}",
            str(DATA_DIR),
            "/run/weblate",
            "/run/gunicorn",
        ]
    )

    print("=> Build assets")
    run(
        [
            "su",
            "-s",
            "/bin/bash",
            HOP3_USER,
            "-c",
            "weblate collectstatic --noinput --clear --link",
        ]
    )
    run(["su", "-s", "/bin/bash", HOP3_USER, "-c", "weblate compress"])

    print("=> Ensure and source celery config overrides")
    # Set default celery options
    os.environ["CELERY_MAIN_OPTIONS"] = ""
    os.environ["CELERY_NOTIFY_OPTIONS"] = ""
    os.environ["CELERY_TRANSLATE_OPTIONS"] = ""
    os.environ["CELERY_BACKUP_OPTIONS"] = ""
    os.environ["CELERY_BEAT_OPTIONS"] = ""
    os.environ["CELERY_MEMORY_OPTIONS"] = ""

    # Create celery.env if not exists
    celery_env = DATA_DIR / "celery.env"
    if not celery_env.exists():
        celery_env.write_text(
            'export CELERY_MAIN_OPTIONS=""\n'
            'export CELERY_NOTIFY_OPTIONS=""\n'
            'export CELERY_TRANSLATE_OPTIONS=""\n'
            'export CELERY_BACKUP_OPTIONS=""\n'
            'export CELERY_BEAT_OPTIONS=""\n'
            'export CELERY_MEMORY_OPTIONS=""\n'
        )

    # Source celery.env
    celery_content = celery_env.read_text()
    for line in celery_content.strip().split("\n"):
        if line.startswith("export "):
            kv = line[7:]
            if "=" in kv:
                key, _, value = kv.partition("=")
                value = value.strip('"').strip("'")
                os.environ[key] = value

    # Required celery env vars
    os.environ["CELERY_WORKER_RUNNING"] = "1"
    celery_broker_url = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}"
    os.environ["CELERY_BROKER_URL"] = celery_broker_url
    os.environ["CELERY_RESULT_BACKEND"] = celery_broker_url

    print("=> Starting supervisor")
    os.execvp(
        "/usr/bin/supervisord",
        [
            "/usr/bin/supervisord",
            "--configuration",
            "/etc/supervisor/supervisord.conf",
            "--nodaemon",
            "-i",
            "weblate",
        ],
    )


if __name__ == "__main__":
    sys.exit(main() or 0)
