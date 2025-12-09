#!/usr/bin/env python3
"""Cal.com start script for Hop3."""

import base64
import json
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
POSTGRES_USERNAME = os.environ.get("POSTGRES_USERNAME", "calcom")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_DATABASE = os.environ.get("POSTGRES_DATABASE", "calcom")

# Redis configuration
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "")
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = os.environ.get("REDIS_PORT", "6379")

# Mail configuration
MAIL_FROM = os.environ.get("MAIL_FROM", "noreply@localhost")
MAIL_FROM_DISPLAY_NAME = os.environ.get("MAIL_FROM_DISPLAY_NAME", "Cal.com")
SMTP_HOST = os.environ.get("SMTP_HOST", "localhost")
SMTP_PORT = os.environ.get("SMTP_PORT", "25")
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

# App configuration
HOP3_APP_ORIGIN = os.environ.get("HOP3_APP_ORIGIN", "http://localhost:3000")


def run(cmd: list[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    return subprocess.run(cmd, check=check, **kwargs)


def generate_base64_secret(length: int = 32) -> str:
    """Generate a base64-encoded random secret."""
    return base64.b64encode(secrets.token_bytes(length)).decode()


def generate_hex_secret(length: int = 24) -> str:
    """Generate a hex-encoded random secret."""
    return secrets.token_hex(length)


def main() -> int:
    print("=> Creating directories")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for d in ["/run/calcom", "/run/yarn", "/run/cache", "/run/calcom/.turbo"]:
        Path(d).mkdir(parents=True, exist_ok=True)

    APP_BASEDIR = CODE_DIR / "calcom"

    # Generate secrets if not exist
    nextauth_secret_file = DATA_DIR / ".nextauth_secret"
    if not nextauth_secret_file.exists():
        print("==> Create NEXTAUTH secret")
        nextauth_secret_file.write_text(generate_base64_secret(32))

    jwt_secret_file = DATA_DIR / ".jwt_secret"
    if not jwt_secret_file.exists():
        print("==> Generate initial app jwt_secret")
        jwt_secret_file.write_text(generate_hex_secret(24))

    calendso_key_file = DATA_DIR / ".calendso_encryption_key"
    if not calendso_key_file.exists():
        print("==> Create CALENDSO encryption key")
        calendso_key_file.write_text(generate_base64_secret(24))

    # Generate VAPID keys
    result = run(
        ["npx", "web-push", "generate-vapid-keys", "--json"],
        capture_output=True,
        text=True,
    )
    vapid_keys = json.loads(result.stdout)
    vapid_public = vapid_keys["publicKey"]
    vapid_private = vapid_keys["privateKey"]

    # Write VAPID keys to file
    Path("/run/calcom/vapid-keys").write_text(result.stdout)

    # Create custom env file if not exists
    env_file = DATA_DIR / "env"
    if not env_file.exists():
        env_file.write_text(
            "# Add custom environment variables in this file\n"
            "NEXT_PUBLIC_LICENSE_CONSENT=true\n"
            "CALCOM_TELEMETRY_DISABLED=true\n"
            "NEXT_PUBLIC_SENTRY_DSN=\n"
            "CALCOM_LICENSE_KEY=\n"
            "API_KEY_PREFIX=cal_\n"
            "IS_SELF_HOSTED=true\n"
        )

    # Build DATABASE_URL
    database_url = (
        f"postgres://{POSTGRES_USERNAME}:{POSTGRES_PASSWORD}@"
        f"{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DATABASE}"
    )

    # Read secrets
    nextauth_secret = nextauth_secret_file.read_text().strip()
    jwt_secret = jwt_secret_file.read_text().strip()
    calendso_key = calendso_key_file.read_text().strip()

    # Set environment variables
    os.environ["DATABASE_URL"] = database_url
    os.environ["DATABASE_DIRECT_URL"] = database_url
    os.environ["NEXTAUTH_SECRET"] = nextauth_secret
    os.environ["JWT_SECRET"] = jwt_secret
    os.environ["CALENDSO_ENCRYPTION_KEY"] = calendso_key

    # Merge configs
    print("=> Merge configs")
    user_env = env_file.read_text()
    combined_env = user_env + f"""
NEXTAUTH_SECRET="{nextauth_secret}"
CALENDSO_ENCRYPTION_KEY="{calendso_key}"
DATABASE_URL="{database_url}"
EMAIL_FROM="{MAIL_FROM}"
EMAIL_FROM_NAME="{MAIL_FROM_DISPLAY_NAME}"
EMAIL_SERVER_HOST="{SMTP_HOST}"
EMAIL_SERVER_PORT="{SMTP_PORT}"
EMAIL_SERVER_USER="{SMTP_USERNAME}"
EMAIL_SERVER_PASSWORD="{SMTP_PASSWORD}"
NEXT_PUBLIC_WEBAPP_URL="{HOP3_APP_ORIGIN}"
REDIS_URL="redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}"
NEXT_PUBLIC_VAPID_PUBLIC_KEY={vapid_public}
VAPID_PRIVATE_KEY={vapid_private}
"""
    Path("/run/calcom/.env").write_text(combined_env)

    # Setup symlinks
    for target, link in [
        ("/run/calcom/.env", APP_BASEDIR / ".env"),
        ("/run/calcom/.turbo", APP_BASEDIR / ".turbo"),
        ("/run/calcom/.env", APP_BASEDIR / "apps" / "api" / "v2" / ".env"),
    ]:
        link_path = Path(link)
        if link_path.exists() or link_path.is_symlink():
            link_path.unlink()
        link_path.symlink_to(target)

    # Migrate DB
    print("==> Migrate DB")
    os.chdir(APP_BASEDIR)
    run(["npx", "prisma", "migrate", "deploy"])

    # Change ownership
    run(["chown", "-R", f"{HOP3_USER}:{HOP3_USER}", str(DATA_DIR), "/run/calcom"])

    # Start Cal.com
    print("==> Starting Cal.com")
    os.execvp(
        "/usr/bin/supervisord",
        [
            "/usr/bin/supervisord",
            "--configuration",
            "/etc/supervisor/supervisord.conf",
            "--nodaemon",
            "-i",
            "Cal.com",
        ],
    )


if __name__ == "__main__":
    sys.exit(main() or 0)
