#!/usr/bin/env python3
"""Startup script for Miniflux."""

import os
import sys


def main() -> None:
    print("==> Starting Miniflux")

    # Convert postgresql:// to postgres:// if needed (Miniflux requires postgres://)
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        if database_url.startswith("postgresql://"):
            database_url = "postgres://" + database_url[len("postgresql://") :]

        # Add sslmode=disable if not present (for internal connections)
        if "sslmode=" not in database_url:
            if "?" in database_url:
                database_url = f"{database_url}&sslmode=disable"
            else:
                database_url = f"{database_url}?sslmode=disable"

        os.environ["DATABASE_URL"] = database_url
        print("==> Database configured")

    # Enable auto-migration and admin creation
    os.environ["RUN_MIGRATIONS"] = "1"
    os.environ["CREATE_ADMIN"] = "1"
    os.environ["ADMIN_USERNAME"] = os.environ.get("ADMIN_USERNAME", "admin")
    os.environ["ADMIN_PASSWORD"] = os.environ.get("ADMIN_PASSWORD", "admin123")

    # Bind to all interfaces
    listen_addr = "0.0.0.0:8080"
    os.environ["LISTEN_ADDR"] = listen_addr

    print(f"==> Starting Miniflux server on {listen_addr}...")
    os.execvp("/app/miniflux", ["/app/miniflux"])


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
