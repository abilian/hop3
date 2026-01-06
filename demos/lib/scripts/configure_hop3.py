#!/usr/bin/env python3
# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Configure hop3-server.toml with demo-specific settings.

This script is copied to the server and executed to:
- Set HOP3_LOG_LEVEL = "DEBUG" for detailed logging
- Generate HOP3_SECRET_KEY if not already set (required for token signing)
- Validate MySQL connection works (fails if MySQL is configured but broken)

It preserves existing settings (like PostgreSQL credentials from the installer).
"""

import secrets
import shutil
import subprocess
import sys
from pathlib import Path

import toml

config_file = Path("/home/hop3/hop3-server.toml")

# Load existing config (installer should have created it with PostgreSQL settings)
if config_file.exists():
    config_data = toml.load(config_file)
else:
    config_data = {}

# Set DEBUG logging for demos
config_data["HOP3_LOG_LEVEL"] = "DEBUG"

# Generate SECRET_KEY if not already set (required for token signing)
if "HOP3_SECRET_KEY" not in config_data:
    config_data["HOP3_SECRET_KEY"] = secrets.token_urlsafe(32)

# Validate MySQL connection if MySQL is installed and configured
if shutil.which("mysql") and "MYSQL_SUPERUSER_PASSWORD" in config_data:
    mysql_user = config_data.get("MYSQL_SUPERUSER", "hop3")
    mysql_password = config_data.get("MYSQL_SUPERUSER_PASSWORD")
    mysql_host = config_data.get("MYSQL_HOST", "127.0.0.1")

    # Test if configured credentials work
    verify_result = subprocess.run(
        ["mysql", "-u", mysql_user, f"-p{mysql_password}", "-h", mysql_host, "-e", "SELECT 1"],
        capture_output=True,
        text=True,
    )

    if verify_result.returncode != 0:
        print(f"ERROR: MySQL connection FAILED with configured credentials!")
        print(f"  User: {mysql_user}, Host: {mysql_host}")
        print(f"  Error: {verify_result.stderr.strip()[:200]}")
        print(f"")
        print(f"  To fix, re-run the installer with: --with mysql")
        print(f"  Or manually create the MySQL user using debian-sys-maint credentials.")
        # Exit with error so the demo launcher knows MySQL is broken
        sys.exit(1)
    else:
        print(f"MySQL connection verified: {mysql_user}@{mysql_host}")

# Write config back
with config_file.open("w") as f:
    f.write("# Hop3 Server Configuration\n")
    f.write("# Settings from installer and demo launcher\n\n")
    toml.dump(config_data, f)

print(f"Config file: {config_file}")
print(f"  HOP3_LOG_LEVEL: {config_data.get('HOP3_LOG_LEVEL', 'NOT SET')}")
print(f"  HOP3_SECRET_KEY: {'SET' if config_data.get('HOP3_SECRET_KEY') else 'NOT SET'}")
print(f"  POSTGRES_HOST: {config_data.get('POSTGRES_HOST', 'NOT SET')}")
print(f"  POSTGRES_SUPERUSER_PASSWORD: {'SET' if config_data.get('POSTGRES_SUPERUSER_PASSWORD') else 'NOT SET'}")
print(f"  MYSQL_HOST: {config_data.get('MYSQL_HOST', 'NOT SET')}")
print(f"  MYSQL_SUPERUSER_PASSWORD: {'SET' if config_data.get('MYSQL_SUPERUSER_PASSWORD') else 'NOT SET'}")
print("Server config updated")
