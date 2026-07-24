# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Systemd service configuration."""

from __future__ import annotations

import secrets
import shutil
import subprocess
from pathlib import Path

from hop3_installer.common import (
    has_systemd,
    print_detail,
    print_success,
    print_warning,
    run_cmd,
)
from hop3_installer.nginx_templates import SYSTEMD_UNIT, UWSGI_UNIT

from .config import ServerInstallerConfig

# ADR 048: canonical home for the JWT signing key — a secrets-tier file,
# 0640 root:hop3, read by both the hop3-server process and the su-hop3 CLI.
SECRET_KEY_FILE = Path("/etc/hop3/secret-key")


def _read_secret_key_file() -> str | None:
    """The signing key already persisted to the canonical file, or None."""
    try:
        return SECRET_KEY_FILE.read_text().strip() or None
    except OSError:
        return None


def _write_secret_key_file(secret_key: str) -> None:
    """
    Persist the signing key to /etc/hop3/secret-key, 0640 root:hop3.

    This is the single source the running service and the su-hop3 CLI both read
    (ADR 048). Mirrors the redis-pass writer: chown is best-effort (the hop3
    group exists by the time systemd setup runs, but stay non-fatal).
    """
    SECRET_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    SECRET_KEY_FILE.write_text(secret_key + "\n")
    SECRET_KEY_FILE.chmod(0o640)
    chown = shutil.which("chown")
    if chown:
        subprocess.run(
            [chown, "root:hop3", str(SECRET_KEY_FILE)],
            check=False,
            capture_output=True,
        )


def setup_environment_file(config: ServerInstallerConfig | None = None) -> str:
    """
    Create /etc/default/hop3 with required environment variables.

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

    # Reuse precedence (ADR 048 §migration): the canonical file if present,
    # else the value the running service currently uses (/etc/default/hop3),
    # else generate. Never rotate an existing key.
    secret_key = (
        _read_secret_key_file() or existing_secret_key or secrets.token_urlsafe(32)
    )

    # Persist to the canonical secrets-tier file — the single source the service
    # and the su-hop3 CLI both read. The HOP3_SECRET_KEY line in /etc/default/hop3
    # (written below) and the copy in hop3-server.toml remain as transitional
    # legacy fallbacks; because the reader prefers this file, the three cannot
    # diverge in effect, so the old desync-→-401 failure mode is closed.
    _write_secret_key_file(secret_key)

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
    """
    Install and enable systemd services.

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


def restart_hop3_server() -> None:
    """
    Restart hop3-server so it reflects the finalized on-disk config.

    ``setup_systemd`` starts hop3-server in step 7, but ``write_server_config``
    writes ``hop3-server.toml`` (OPERATOR_EMAIL, DB creds, ADMIN_DOMAIN) only
    after the DB steps. ``ConfigLoader`` reads the file once at process start and
    caches it, so on a fresh box — where the toml did not yet exist when the
    service first booted — those keys stay invisible to the running process
    (a Docker redeploy masks this: the file already exists at boot). Without
    this restart the server silently serves a stale config and every
    ``[admin].email = "operator"`` app fails to deploy with "no operator email".

    Package-manager-aware: systemctl on systemd hosts, supervisorctl otherwise.
    A failed restart is surfaced by ``verify_installation`` (it checks the
    service is active), so warn here rather than abort.
    """
    if has_systemd():
        result = run_cmd(["systemctl", "restart", "hop3-server"], check=False)
    else:
        result = run_cmd(["supervisorctl", "restart", "hop3-server"], check=False)

    if result.returncode == 0:
        print_success("hop3-server restarted to load final config")
    else:
        print_warning("Failed to restart hop3-server after writing config")
        print_detail("The server may be serving a stale config; see logs above.")
