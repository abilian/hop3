#!/usr/bin/env python3
"""Startup script for Ghost CMS."""

import json
import os
import sys
from pathlib import Path


def main() -> None:
    print("==> Starting Ghost CMS")

    # Get configuration from environment
    host_name = os.environ.get("HOST_NAME", "localhost")
    port = os.environ.get("PORT", "2368")
    database_url = os.environ.get("DATABASE_URL")

    # Build config
    config = {
        "url": f"https://{host_name}",
        "server": {
            "port": int(port),
            "host": "::",
        },
        "logging": {
            "transports": ["stdout"],
        },
        "paths": {
            "contentPath": "/var/lib/ghost/content",
        },
    }

    # Configure database if DATABASE_URL is set
    if database_url:
        # Parse MySQL URL: mysql://user:pass@host:port/database
        from urllib.parse import urlparse

        parsed = urlparse(database_url)
        config["database"] = {
            "client": "mysql",
            "connection": {
                "host": parsed.hostname or "localhost",
                "port": parsed.port or 3306,
                "user": parsed.username or "ghost",
                "password": parsed.password or "",
                "database": parsed.path.lstrip("/") if parsed.path else "ghost",
            },
        }
        print("==> Database configured from DATABASE_URL")
    else:
        # Default to SQLite
        config["database"] = {
            "client": "sqlite3",
            "connection": {
                "filename": "/var/lib/ghost/content/data/ghost.db",
            },
        }
        print("==> Using SQLite database")

    # Write config
    config_path = Path("/var/lib/ghost/config.production.json")
    config_path.write_text(json.dumps(config, indent=2))
    print(f"==> Configuration written to {config_path}")

    # Start Ghost
    print("==> Starting Ghost server")
    os.chdir("/var/lib/ghost")
    os.execvp("node", ["node", "current/index.js"])


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
