#!/usr/bin/env python3
"""Umami start script for Hop3."""

import os
import secrets
import subprocess
import sys
from pathlib import Path

# Environment configuration
DATA_DIR = Path(os.environ.get("HOP3_DATA_DIR", "/app/data"))
CODE_DIR = Path(os.environ.get("HOP3_CODE_DIR", "/app/code"))
PKG_DIR = Path(os.environ.get("HOP3_PKG_DIR", "/app/pkg"))
HOP3_USER = os.environ.get("HOP3_USER", "www-data")

# Database configuration
POSTGRES_USERNAME = os.environ.get("POSTGRES_USERNAME", "umami")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_DATABASE = os.environ.get("POSTGRES_DATABASE", "umami")


def run(cmd: list[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    return subprocess.run(cmd, check=check, **kwargs)


def generate_hash_salt(length: int = 32) -> str:
    """Generate a random hash salt."""
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def main() -> int:
    # Create env.sh if not exists
    env_file = DATA_DIR / "env.sh"
    if not env_file.exists():
        template = PKG_DIR / "env.sh.template"
        if template.exists():
            content = template.read_text()
            hash_salt = generate_hash_salt()
            content = content.replace("HASH_SALT=change_me_to_random_string", f"HASH_SALT={hash_salt}")
            env_file.write_text(content)
        else:
            hash_salt = generate_hash_salt()
            env_file.write_text(f"export HASH_SALT={hash_salt}\n")

    print("==> Changing ownership")
    run(["chown", "-R", f"{HOP3_USER}:{HOP3_USER}", str(DATA_DIR)])

    # Set standard env vars
    os.environ["NODE_ENV"] = "production"
    os.environ["DATABASE_URL"] = (
        f"postgresql://{POSTGRES_USERNAME}:{POSTGRES_PASSWORD}@"
        f"{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DATABASE}"
    )
    os.environ["FORCE_SSL"] = "1"
    os.environ["PORT"] = "3000"
    os.environ["DISABLE_UPDATES"] = "1"
    os.environ["DATABASE_TYPE"] = "postgresql"

    # Source env.sh
    env_content = env_file.read_text()
    for line in env_content.strip().split("\n"):
        if line.startswith("export "):
            kv = line[7:]
            if "=" in kv:
                key, _, value = kv.partition("=")
                os.environ[key] = value

    # Create pgcrypto extension
    run(
        [
            "psql",
            "-h",
            POSTGRES_HOST,
            "-p",
            POSTGRES_PORT,
            "-U",
            POSTGRES_USERNAME,
            "-d",
            POSTGRES_DATABASE,
            "-c",
            "CREATE EXTENSION IF NOT EXISTS pgcrypto;",
        ],
        env={**os.environ, "PGPASSWORD": POSTGRES_PASSWORD},
        check=False,
    )

    # Run build
    print("=> Running build script that generates the migrations")
    os.chdir(CODE_DIR)
    run(["yarn", "run", "build"], env={**os.environ, "VERCEL": "1"})

    # Run migrations
    print("=> Running migrations")
    run(
        [
            "su",
            "-s",
            "/bin/bash",
            HOP3_USER,
            "-c",
            "yarn run update-db",
        ],
        cwd=CODE_DIR,
    )

    # Start Umami
    print("==> Starting Umami")
    os.execvp(
        "su",
        [
            "su",
            "-s",
            "/bin/bash",
            HOP3_USER,
            "-c",
            f"cd {CODE_DIR} && yarn next start",
        ],
    )


if __name__ == "__main__":
    sys.exit(main() or 0)
