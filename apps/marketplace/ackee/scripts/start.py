#!/usr/bin/env python3
"""Ackee start script for Hop3."""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Environment configuration
DATA_DIR = Path(os.environ.get("HOP3_DATA_DIR", "/app/data"))
PKG_DIR = Path(os.environ.get("HOP3_PKG_DIR", "/app/pkg"))
HOP3_USER = os.environ.get("HOP3_USER", "www-data")

# MongoDB configuration
MONGODB_URL = os.environ.get("MONGODB_URL", "")
MONGODB_USERNAME = os.environ.get("MONGODB_USERNAME", "ackee")
MONGODB_PASSWORD = os.environ.get("MONGODB_PASSWORD", "")
MONGODB_HOST = os.environ.get("MONGODB_HOST", "localhost")
MONGODB_PORT = os.environ.get("MONGODB_PORT", "27017")
MONGODB_DATABASE = os.environ.get("MONGODB_DATABASE", "ackee")


def run(cmd: list[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    return subprocess.run(cmd, check=check, **kwargs)


def main() -> int:
    # Ensure env file exists
    env_file = DATA_DIR / "env"
    if not env_file.exists():
        template = PKG_DIR / "templates" / "env.template"
        shutil.copy(template, env_file)

    # Build MongoDB URL
    if MONGODB_URL:
        mongodb_connection = MONGODB_URL
    else:
        mongodb_connection = (
            f"mongodb://{MONGODB_USERNAME}:{MONGODB_PASSWORD}@"
            f"{MONGODB_HOST}:{MONGODB_PORT}/{MONGODB_DATABASE}"
        )

    # Update env file with MongoDB URL
    content = env_file.read_text()
    content = re.sub(
        r"ACKEE_MONGODB=.*",
        f"ACKEE_MONGODB={mongodb_connection}",
        content,
    )
    env_file.write_text(content)

    # Link env file
    code_env = Path("/app/code/.env")
    if code_env.exists() or code_env.is_symlink():
        code_env.unlink()
    code_env.symlink_to(env_file)

    # Change ownership
    print("==> Changing ownership")
    run(["chown", "-R", f"{HOP3_USER}:{HOP3_USER}", str(DATA_DIR)])

    # Set environment
    os.environ["NODE_ENV"] = "production"

    # Start Ackee
    print("==> Starting Ackee")
    os.chdir("/app/code")
    os.execvp(
        "su",
        ["su", "-s", "/bin/bash", HOP3_USER, "-c", "cd /app/code && npm run server"],
    )


if __name__ == "__main__":
    sys.exit(main() or 0)
