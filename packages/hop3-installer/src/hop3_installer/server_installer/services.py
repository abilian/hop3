# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Systemd service configuration."""

from __future__ import annotations

import secrets
from pathlib import Path

from hop3_installer.common import print_detail, print_success, print_warning, run_cmd

from .config import SYSTEMD_UNIT, UWSGI_UNIT


def setup_environment_file() -> str:
    """Create /etc/default/hop3 with required environment variables.

    Returns:
        The secret key (either existing or newly generated)
    """
    env_file = Path("/etc/default/hop3")

    # Check if file already exists and has HOP3_SECRET_KEY
    if env_file.exists():
        content = env_file.read_text()
        for line in content.splitlines():
            if line.startswith("HOP3_SECRET_KEY="):
                return line.split("=", 1)[1].strip()

    # Generate a secure secret key
    secret_key = secrets.token_urlsafe(32)

    # Write the environment file
    env_content = f"""# Hop3 Server Environment Variables
# This file is loaded by the hop3-server systemd service

# Secret key for JWT token signing (required for authentication)
HOP3_SECRET_KEY={secret_key}
"""
    env_file.write_text(env_content)
    env_file.chmod(0o600)  # Restrict permissions

    return secret_key


def setup_systemd() -> str:
    """Install and enable systemd services.

    Returns:
        The secret key from the environment file
    """
    # Create environment file first
    secret_key = setup_environment_file()

    # Hop3 server service
    service_path = Path("/etc/systemd/system/hop3-server.service")
    service_path.write_text(SYSTEMD_UNIT)

    # uWSGI service
    uwsgi_path = Path("/etc/systemd/system/uwsgi-hop3.service")
    uwsgi_path.write_text(UWSGI_UNIT)

    # Reload and enable
    run_cmd(["systemctl", "daemon-reload"])
    run_cmd(["systemctl", "enable", "hop3-server"], check=False)
    run_cmd(["systemctl", "enable", "uwsgi-hop3"], check=False)

    # Start services and check for errors
    services_ok = True

    result = run_cmd(["systemctl", "start", "hop3-server"], check=False)
    if result.returncode != 0:
        services_ok = False
        print_warning("Failed to start hop3-server service")
        print_detail("Check status with: journalctl -u hop3-server -n 50")

    result = run_cmd(["systemctl", "start", "uwsgi-hop3"], check=False)
    if result.returncode != 0:
        services_ok = False
        print_warning("Failed to start uwsgi-hop3 service")
        print_detail("Check status with: journalctl -u uwsgi-hop3 -n 50")

    if services_ok:
        print_success("Systemd services configured and started")
    else:
        print_warning("Systemd services configured but some failed to start")

    return secret_key
