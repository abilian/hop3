# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Redis configuration."""

from __future__ import annotations

import re
import secrets
from pathlib import Path

from hop3_installer.common import (
    CommandError,
    InstallStepError,
    control_service,
    has_systemd,
    print_detail,
    print_info,
    print_success,
    run_cmd,
)

from .docker_utils import get_docker_bridge_ip

# Common Redis config file locations
REDIS_CONF_PATHS = [
    Path("/etc/redis/redis.conf"),
    Path("/etc/redis.conf"),
]

#: Service names, in order: Debian ships `redis-server`, Fedora `redis`.
_REDIS_SERVICE_NAMES = ("redis-server", "redis")

# Persistent location for the Redis auth password. The hop3-server
# process (running as user `hop3`) reads this file at runtime; setting
# it 0640 root:hop3 keeps it off any ps/argv path while still letting
# the addon plugin authenticate.
REDIS_PASS_FILE = Path("/etc/hop3/redis-pass")


def _ensure_redis_password() -> str:
    """
    Generate (or load) the Redis auth password and persist it.

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


def fix_redis_pass_ownership(*, required: bool = False) -> None:
    """
    Re-apply root:hop3 ownership on the redis password file.

    Called when the password is generated, which on a first install may be
    before the hop3 group exists, and again after the user is created. That
    second call is ``required``: without the group, hop3-server cannot read
    the password and every redis addon fails to authenticate.
    """
    if not REDIS_PASS_FILE.exists():
        return
    result = run_cmd(["chown", "root:hop3", str(REDIS_PASS_FILE)], check=False)
    if required and result.returncode != 0:
        raise CommandError(
            cmd=["chown", "root:hop3", str(REDIS_PASS_FILE)],
            returncode=result.returncode,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
        )


def _write_redis_config() -> str | None:
    """
    Make this Redis a primary and, with a Docker bridge, reachable from it.

    Edits the config file, the only change a restart keeps: the runtime
    ``CONFIG SET replica-read-only no`` and ``REPLICAOF NO ONE`` this replaced
    ran before the restart, which discarded them.

    Returns:
        The auth password, when one was set (Docker bridge), else None.

    Raises:
        InstallStepError: no Redis config file.
    """
    redis_conf = next((p for p in REDIS_CONF_PATHS if p.exists()), None)
    if redis_conf is None:
        paths = ", ".join(str(p) for p in REDIS_CONF_PATHS)
        msg = f"no Redis configuration file found ({paths})"
        raise InstallStepError(msg)

    original = redis_conf.read_text()
    # A replica refuses writes ("You can't write against a read only replica").
    content = re.sub(
        r"^\s*(replicaof|slaveof)\s+.*\n?", "", original, flags=re.MULTILINE
    )

    password = None
    docker_ip = get_docker_bridge_ip()
    if docker_ip:
        password = _ensure_redis_password()
        content, _ = _update_redis_bind(content, docker_ip)
        content, _ = _update_redis_requirepass(content, password)
    else:
        print_detail("No Docker bridge: Redis binds to localhost only")

    if content != original:
        redis_conf.write_text(content)
    return password


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
    """
    Ensure Redis is configured with the persisted requirepass.

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
    """
    Configure Redis for Hop3: a primary, bound for Docker access, running.

    Raises:
        CommandError, InstallStepError: Redis is not configured and answering.
    """
    print_info("Configuring Redis...")
    password = _write_redis_config()

    # Through `control_service`, so this works without systemd and finds the
    # unit under its Debian or Fedora name.
    if has_systemd() and not control_service("enable", *_REDIS_SERVICE_NAMES):
        msg = f"Redis could not be enabled (tried: {', '.join(_REDIS_SERVICE_NAMES)})"
        raise InstallStepError(msg)
    if not control_service("restart", *_REDIS_SERVICE_NAMES):
        msg = "Redis did not restart, so apps with a redis addon cannot connect"
        raise InstallStepError(msg)

    # With requirepass set, an unauthenticated PING answers NOAUTH.
    env = {"REDISCLI_AUTH": password} if password else None
    result = run_cmd(["redis-cli", "PING"], check=False, env=env)
    if "PONG" not in (result.stdout or ""):
        raise CommandError(
            cmd=["redis-cli", "PING"],
            returncode=result.returncode,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
        )
    print_success("Redis configured and running")
