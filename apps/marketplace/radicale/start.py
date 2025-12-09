#!/usr/bin/env python3
"""Startup script for Radicale CalDAV/CardDAV Server."""

import os
import sys
from pathlib import Path

CONFIG = """\
[server]
hosts = 0.0.0.0:5232

[auth]
# For demo purposes, use htpasswd authentication
# In production, configure LDAP or other auth methods
type = htpasswd
htpasswd_filename = /app/data/htpasswd
htpasswd_encryption = bcrypt

[rights]
type = from_file
file = /app/rights

[storage]
type = multifilesystem
filesystem_folder = /app/data/collections

[web]
type = internal

[logging]
level = warning
"""


def main() -> None:
    print("==> Starting Radicale CalDAV/CardDAV Server")

    # Create data directories
    collections_dir = Path("/app/data/collections")
    collections_dir.mkdir(parents=True, exist_ok=True)

    # Generate config from template
    print("==> Generating configuration")
    Path("/app/config").write_text(CONFIG)

    # Create default htpasswd file if not exists
    # Default user: demo / demo
    htpasswd_path = Path("/app/data/htpasswd")
    if not htpasswd_path.exists():
        print("==> Creating default user (demo/demo)")
        # bcrypt hash for "demo"
        htpasswd_path.write_text(
            "demo:$2b$12$LQv3c1yqBWVHxkd0LHAkCO.NKHLvxhCd7C0YcY6PtFaKXBjrCPvAu\n"
        )

    print("==> Starting Radicale on port 5232")
    os.execvp("python", ["python", "-m", "radicale", "--config", "/app/config"])


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
