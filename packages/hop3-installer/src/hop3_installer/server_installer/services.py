# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Systemd service configuration."""

from __future__ import annotations

import secrets
from pathlib import Path

from hop3_installer.common import print_detail, print_success, print_warning, run_cmd
from hop3_installer.nginx_templates import SYSTEMD_UNIT, UWSGI_UNIT

from .config import ServerInstallerConfig


def setup_environment_file(config: ServerInstallerConfig | None = None) -> str:
    """Create /etc/default/hop3 with required environment variables.

    Args:
        config: Server installer config with ACME settings

    Returns:
        The secret key (either existing or newly generated)
    """
    env_file = Path("/etc/default/hop3")
    existing_secret_key = None
    existing_acme_email = None

    # Reuse what a prior install / the operator already set, so a redeploy
    # doesn't rotate the secret key or silently revert certbot to self-signed.
    # (The engine is derived from email presence below, so we only need the
    # email back.)
    if env_file.exists():
        content = env_file.read_text()
        for line in content.splitlines():
            if line.startswith("HOP3_SECRET_KEY="):
                existing_secret_key = line.split("=", 1)[1].strip()
            elif line.startswith("ACME_EMAIL="):
                existing_acme_email = line.split("=", 1)[1].strip()

    # Use existing or generate a new secret key
    secret_key = existing_secret_key or secrets.token_urlsafe(32)

    # ACME precedence: an explicit --acme-email wins; otherwise PRESERVE whatever
    # is already configured (don't revert the operator's certbot setup on a
    # plain redeploy). Self-signed only on a truly fresh install.
    cli_email = config.acme_email if config and config.acme_email else ""
    acme_email = cli_email or existing_acme_email or ""

    # Write the environment file
    env_content = f"""# Hop3 Server Environment Variables
# This file is loaded by the hop3-server systemd service

# Secret key for JWT token signing (required for authentication)
HOP3_SECRET_KEY={secret_key}

# ACME/Let's Encrypt Configuration
# Set to 'certbot' to use Let's Encrypt (requires valid ACME_EMAIL)
# Set to 'self-signed' for self-signed certificates (default)
"""

    # Only enable certbot if email is provided
    if acme_email:
        env_content += "ACME_ENGINE=certbot\n"
        env_content += f"ACME_EMAIL={acme_email}\n"
    else:
        env_content += """ACME_ENGINE=self-signed
# To enable Let's Encrypt certificates, set both:
#   ACME_ENGINE=certbot
#   ACME_EMAIL=your@email.com
"""

    env_file.write_text(env_content)
    env_file.chmod(0o600)  # Restrict permissions

    return secret_key


def setup_systemd(config: ServerInstallerConfig | None = None) -> str:
    """Install and enable systemd services.

    Args:
        config: Server installer config with ACME settings

    Returns:
        The secret key from the environment file
    """
    # Create environment file first (with ACME configuration)
    secret_key = setup_environment_file(config)

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

    # RESTART, not start: this step just (re)wrote the unit files and the
    # EnvironmentFile (/etc/default/hop3, with ACME_ENGINE/secret key). On a
    # redeploy the service is already running, so `systemctl start` is a no-op
    # and the process keeps its STALE environment — the new ACME engine never
    # takes effect (it silently reports success while serving the old config).
    # `restart` starts a stopped service and reloads config on a running one.
    services_ok = True

    result = run_cmd(["systemctl", "restart", "hop3-server"], check=False)
    if result.returncode != 0:
        services_ok = False
        print_warning("Failed to restart hop3-server service")
        print_detail("Check status with: journalctl -u hop3-server -n 50")

    result = run_cmd(["systemctl", "restart", "uwsgi-hop3"], check=False)
    if result.returncode != 0:
        services_ok = False
        print_warning("Failed to restart uwsgi-hop3 service")
        print_detail("Check status with: journalctl -u uwsgi-hop3 -n 50")

    if services_ok:
        print_success("Systemd services configured and (re)started")
    else:
        print_warning("Systemd services configured but some failed to start")

    return secret_key
