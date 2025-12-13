#!/usr/bin/env python3
"""Startup script for Umami Analytics."""
from __future__ import annotations

import os
import secrets
import subprocess
import sys


def generate_hash_salt() -> str:
    """Generate a random 32-character alphanumeric string."""
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(32))


def main() -> None:
    print("==> Starting Umami Analytics")

    # Generate HASH_SALT if not provided
    if not os.environ.get("HASH_SALT"):
        os.environ["HASH_SALT"] = generate_hash_salt()
        print("Generated HASH_SALT")

    # Run database migrations
    print("==> Running database migrations")
    subprocess.run(["yarn", "prisma", "migrate", "deploy"], check=True)

    # Start Umami (using standalone server for Next.js 15+)
    print("==> Starting Next.js standalone server")
    os.execvp("node", ["node", ".next/standalone/server.js"])


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
