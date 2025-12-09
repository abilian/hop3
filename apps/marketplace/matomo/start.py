#!/usr/bin/env python3
"""Startup script for Matomo Analytics."""

import os
import sys


def main() -> None:
    print("==> Starting Matomo Analytics")

    # Get database configuration from environment
    database_url = os.environ.get("DATABASE_URL")

    if database_url:
        from urllib.parse import urlparse

        parsed = urlparse(database_url)
        os.environ["MATOMO_DATABASE_HOST"] = parsed.hostname or "localhost"
        os.environ["MATOMO_DATABASE_USERNAME"] = parsed.username or "matomo"
        os.environ["MATOMO_DATABASE_PASSWORD"] = parsed.password or ""
        os.environ["MATOMO_DATABASE_DBNAME"] = parsed.path.lstrip("/") if parsed.path else "matomo"

        print("==> Database configured from DATABASE_URL")
        print(f"    Host: {os.environ['MATOMO_DATABASE_HOST']}")
        print(f"    Database: {os.environ['MATOMO_DATABASE_DBNAME']}")

    # Start Apache
    print("==> Starting Apache")
    os.execvp("apache2-foreground", ["apache2-foreground"])


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
