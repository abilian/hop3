#!/usr/bin/env python3
"""Startup script for Listmonk."""

import os
import subprocess
import sys
from urllib.parse import urlparse


def parse_database_url(url: str) -> dict:
    """Parse PostgreSQL DATABASE_URL into components."""
    parsed = urlparse(url)
    return {
        "user": parsed.username or "",
        "password": parsed.password or "",
        "host": parsed.hostname or "",
        "port": str(parsed.port) if parsed.port else "5432",
        "database": parsed.path.lstrip("/") if parsed.path else "",
    }


def main() -> None:
    print("==> Starting Listmonk")

    # Parse DATABASE_URL to extract components
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        db_config = parse_database_url(database_url)

        os.environ["LISTMONK_db__user"] = db_config["user"]
        os.environ["LISTMONK_db__password"] = db_config["password"]
        os.environ["LISTMONK_db__host"] = db_config["host"]
        os.environ["LISTMONK_db__port"] = db_config["port"]
        os.environ["LISTMONK_db__database"] = db_config["database"]

        print("==> Database config:")
        print(f"    Host: {db_config['host']}")
        print(f"    Port: {db_config['port']}")
        print(f"    User: {db_config['user']}")
        print(f"    Database: {db_config['database']}")

    # Set SSL mode (disable for internal connections)
    os.environ["LISTMONK_db__ssl_mode"] = "disable"

    # Bind to all interfaces on port 9000
    os.environ["LISTMONK_app__address"] = "0.0.0.0:9000"

    # Set default admin credentials for demo
    os.environ["LISTMONK_ADMIN_USER"] = os.environ.get("ADMIN_USER", "admin")
    os.environ["LISTMONK_ADMIN_PASSWORD"] = os.environ.get("ADMIN_PASSWORD", "admin123")

    print("==> Running database migrations and install...")
    # Install creates the database schema and default admin user
    subprocess.run(
        ["./listmonk", "--install", "--idempotent", "--yes", "--config="], check=True
    )

    print("==> Starting Listmonk server...")
    os.execvp("./listmonk", ["./listmonk", "--config="])


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
