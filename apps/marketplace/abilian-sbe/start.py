#!/usr/bin/env python3
"""Startup script for Abilian SBE."""

import os
import sys


def main() -> None:
    print("==> Starting Abilian SBE")

    port = os.environ.get("PORT", "8000")

    # Configure database from DATABASE_URL if available
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        os.environ["SQLALCHEMY_DATABASE_URI"] = database_url
        print("==> Database configured from DATABASE_URL")

    # Configure Redis from REDIS_URL if available
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        os.environ["REDIS_URI"] = redis_url
        print("==> Redis configured from REDIS_URL")

    # Add venv to PATH
    path = os.environ.get("PATH", "")
    os.environ["PATH"] = f".venv/bin:{path}"

    # Start Gunicorn
    print(f"==> Starting Gunicorn on port {port}")
    os.execvp(
        ".venv/bin/gunicorn",
        [
            "gunicorn",
            "abilian.sbe.app:create_app()",
            "-b",
            f"0.0.0.0:{port}",
            "--workers",
            "4",
            "--log-level",
            "info",
            "--log-file",
            "-",
        ],
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
