# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Redis configuration."""

from __future__ import annotations

import re
import secrets
import shutil
import subprocess
from pathlib import Path

from hop3_installer.common import (
    print_detail,
    print_info,
    print_success,
    print_warning,
    run_cmd,
)

from .docker_utils import get_docker_bridge_ip

# Common Redis config file locations
REDIS_CONF_PATHS = [
    Path("/etc/redis/redis.conf"),
    Path("/etc/redis.conf"),
]

# Persistent location for the Redis auth password. The hop3-server
# process (running as user `hop3`) reads this file at runtime; setting
# it 0640 root:hop3 keeps it off any ps/argv path while still letting
# the addon plugin authenticate.
REDIS_PASS_FILE = Path("/etc/hop3/redis-pass")


def _ensure_redis_password() -> str:
    """Generate (or load) the Redis auth password and persist it.

    The file is written 0640 root:hop3 so the hop3-server process can
    read it while keeping it inaccessible to other local users. If the
    hop3 group does not exist yet (first-run order quirk), we leave the
    ownership as root:root and rely on the ``fix_redis_pass_ownership``
    pass once the user has been created.
    """
    REDIS_PASS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if REDIS_PASS_FILE.exists() and REDIS_PASS_FILE.read_text().strip():
        return REDIS_PASS_FILE.read_text().strip()

    password = secrets.token_urlsafe(32)
    REDIS_PASS_FILE.write_text(password + "\n")
    REDIS_PASS_FILE.chmod(0o640)
    fix_redis_pass_ownership()
    print_detail("Redis password generated and persisted")
    return password


def fix_redis_pass_ownership() -> None:
    """Re-apply root:hop3 ownership on the redis password file.

    Safe to call repeatedly; called both at password generation time and
    after the hop3 user is created (which may happen *after* Redis is
    configured on first install).
    """
    if not REDIS_PASS_FILE.exists():
        return
    chown = shutil.which("chown")
    if not chown:
        return
    subprocess.run(
        [chown, "root:hop3", str(REDIS_PASS_FILE)],
        check=False,
        capture_output=True,
    )


def _configure_redis_bind() -> None:
    """Configure Redis to bind to localhost and Docker bridge.

    This allows Docker containers to connect to Redis via host.docker.internal
    while keeping Redis inaccessible from external networks.
    """
    # Find Redis config file
    redis_conf = next((p for p in REDIS_CONF_PATHS if p.exists()), None)
    if not redis_conf:
        print_warning("Redis config file not found, skipping bind configuration")
        return

    # Get Docker bridge IP
    docker_ip = get_docker_bridge_ip()
    if not docker_ip:
        print_detail("Docker bridge not found, Redis will bind to localhost only")
        return

    password = _ensure_redis_password()

    content = redis_conf.read_text()
    content, bind_modified = _update_redis_bind(content, docker_ip)
    content, requirepass_modified = _update_redis_requirepass(content, password)
    modified = bind_modified or requirepass_modified

    if modified:
        redis_conf.write_text(content)
        print_detail("Redis configured to accept connections from Docker containers")


def _update_redis_bind(content: str, docker_ip: str) -> tuple[str, bool]:
    """Update Redis bind directive to include Docker bridge IP."""
    new_bind = f"bind 127.0.0.1 {docker_ip}"

    if docker_ip in content:
        print_detail(f"Redis already configured for Docker bridge ({docker_ip})")
        return content, False

    if re.search(r"^bind\s+", content, re.MULTILINE):
        content = re.sub(r"^bind\s+.*$", new_bind, content, flags=re.MULTILINE)
        print_detail(f"Updated Redis bind to: {new_bind}")
    else:
        content = f"{new_bind}\n{content}"
        print_detail(f"Added Redis bind: {new_bind}")
    return content, True


def _update_redis_requirepass(content: str, password: str) -> tuple[str, bool]:
    """Ensure Redis is configured with the persisted requirepass.

    Replaces the previous ``_update_redis_protected_mode`` helper, which
    disabled protected-mode for Docker bridge access *without* setting
    a password — leaving Redis listening on the bridge with no auth.
    Now we keep protected-mode at its default and require auth instead.
    """
    target_line = f"requirepass {password}"
    if target_line in content:
        print_detail("Redis requirepass already up to date")
        return content, False

    if re.search(r"^#?\s*requirepass\s+", content, re.MULTILINE):
        content = re.sub(
            r"^#?\s*requirepass\s+.*$",
            target_line,
            content,
            flags=re.MULTILINE,
        )
    else:
        content = f"{target_line}\n{content}"
    print_detail("Configured Redis requirepass")
    return content, True


def configure_redis() -> None:
    """Configure Redis for Hop3 use.

    Ensures Redis is:
    - Running as a primary (not a replica)
    - Bound to localhost and Docker bridge (for container access)
    - Enabled and started
    """
    print_info("Configuring Redis...")

    # Configure bind address for Docker access
    _configure_redis_bind()

    # Ensure Redis is not configured as a replica
    # This fixes the "You can't write against a read only replica" error
    result = run_cmd(
        ["redis-cli", "CONFIG", "SET", "replica-read-only", "no"],
        check=False,
    )
    if result.returncode != 0:
        print_warning(
            "Could not set replica-read-only=no (Redis may not be running yet)"
        )

    # Remove any replicaof configuration (make this a primary)
    result = run_cmd(
        ["redis-cli", "REPLICAOF", "NO", "ONE"],
        check=False,
    )
    if result.returncode == 0:
        print_detail("Redis configured as primary (not replica)")

    # Enable and restart Redis service (restart to apply bind changes)
    run_cmd(["systemctl", "enable", "redis-server"], check=False)
    run_cmd(["systemctl", "restart", "redis-server"], check=False)

    # Verify Redis is working
    result = run_cmd(["redis-cli", "PING"], check=False)
    if result.returncode == 0 and "PONG" in result.stdout:
        print_success("Redis configured and running")
    else:
        print_warning("Redis may not be running correctly")
