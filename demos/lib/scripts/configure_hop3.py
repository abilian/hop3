#!/usr/bin/env python3
# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Configure hop3-server.toml with demo-specific settings.

This script is copied to the server and executed to:
- Set HOP3_LOG_LEVEL = "DEBUG" for detailed logging
- Generate HOP3_SECRET_KEY if not already set (required for token signing)

It preserves existing settings (like PostgreSQL credentials from the installer).
"""

import secrets
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

# Write config back
with config_file.open("w") as f:
    f.write("# Hop3 Server Configuration\n")
    f.write("# PostgreSQL settings from installer, DEBUG logging from demo launcher\n\n")
    toml.dump(config_data, f)

print(f"Config file: {config_file}")
print(f"  HOP3_LOG_LEVEL: {config_data.get('HOP3_LOG_LEVEL', 'NOT SET')}")
print(f"  HOP3_SECRET_KEY: {'SET' if config_data.get('HOP3_SECRET_KEY') else 'NOT SET'}")
print(f"  POSTGRES_HOST: {config_data.get('POSTGRES_HOST', 'NOT SET')}")
print(f"  POSTGRES_SUPERUSER_PASSWORD: {'SET' if config_data.get('POSTGRES_SUPERUSER_PASSWORD') else 'NOT SET'}")
print("Server config updated")
