#!/usr/bin/env python3
"""Startup script for HedgeDoc."""

import json
import os
import secrets
import sys
from pathlib import Path


def generate_secret() -> str:
    """Generate a random 32-character alphanumeric string."""
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(32))


def main() -> None:
    print("==> Starting HedgeDoc")

    # Create directories
    Path("/app/uploads").mkdir(parents=True, exist_ok=True)
    Path("/app/tmp").mkdir(parents=True, exist_ok=True)

    # Generate session secret if not set
    if not os.environ.get("CMD_SESSION_SECRET"):
        os.environ["CMD_SESSION_SECRET"] = generate_secret()
        print("Generated CMD_SESSION_SECRET")

    # Use DATABASE_URL if CMD_DB_URL not set
    if not os.environ.get("CMD_DB_URL") and os.environ.get("DATABASE_URL"):
        os.environ["CMD_DB_URL"] = os.environ["DATABASE_URL"]
        print("Set CMD_DB_URL from DATABASE_URL")

    # Set domain from HOST_NAME if available
    if not os.environ.get("CMD_DOMAIN") and os.environ.get("HOST_NAME"):
        os.environ["CMD_DOMAIN"] = os.environ["HOST_NAME"]
        print(f"Set CMD_DOMAIN from HOST_NAME: {os.environ['CMD_DOMAIN']}")

    # Set PORT for internal use
    internal_port = int(os.environ.get("PORT", "3000"))

    # Debug: show key env vars
    print(f"CMD_DB_URL: {os.environ.get('CMD_DB_URL', 'NOT SET')}")
    print(f"CMD_DOMAIN: {os.environ.get('CMD_DOMAIN', 'NOT SET')}")
    print(f"INTERNAL_PORT: {internal_port}")

    # Create config.json for HedgeDoc (required in production mode)
    config = {
        "production": {
            "db": {
                "dialect": "postgres",
                "url": os.environ.get("CMD_DB_URL", ""),
            },
            "port": internal_port,
            "domain": os.environ.get("CMD_DOMAIN", "localhost"),
            "protocolUseSSL": True,
            "allowAnonymous": True,
            "allowAnonymousEdits": True,
            "allowFreeURL": True,
            "defaultPermission": "freely",
            "sessionSecret": os.environ.get("CMD_SESSION_SECRET", ""),
            "uploadsPath": "/app/uploads",
        }
    }

    config_path = Path("/app/config.json")
    config_path.write_text(json.dumps(config, indent=2))

    print("==> Created config.json")
    print(config_path.read_text())

    # Start HedgeDoc
    print("==> Starting Node.js server")
    os.execvp("node", ["node", "app.js"])


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
