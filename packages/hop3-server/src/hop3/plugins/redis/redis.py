# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Redis service implementation.

This module implements the Addon protocol for Redis,
allowing applications to attach to a Redis instance.

Unlike PostgreSQL, Redis doesn't require per-addon database creation.
Each addon is assigned a dedicated database number (1-15) for isolation;
db 0 is reserved (assignments are persisted in the addon-secrets store so
they survive restarts and don't depend on Python's hash randomization).
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hop3.config import HOP3_ROOT
from hop3.core.backup import resolve_backup_file
from hop3.core.identifiers import validate_service_name
from hop3.plugins.addons import (
    delete_addon_secrets,
    load_addon_secrets,
    save_addon_secrets,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

# Addon type identifier for secrets storage
ADDON_TYPE = "redis"

# Redis ships with 16 logical databases (0-15). db 0 is reserved for hop3
# internal/probing use; addons are assigned a number in [1, 15].
RESERVED_DB = 0
MIN_ADDON_DB = 1
MAX_ADDON_DB = 15

# Held while a db number is chosen and written down, so the choice and the
# record cannot be split by another create. Lives beside the secrets it
# guards; the `.lock` suffix keeps it out of the `*.json` scan.
DB_NUMBER_LOCK_FILE = ".db-numbers.lock"

# Persistent file written by the installer holding the Redis auth
# password. Absent means the install has not (yet) been switched to
# auth mode — we fall back to unauthenticated calls so legacy installs
# keep working until they re-run the installer.
REDIS_PASS_FILE = Path("/etc/hop3/redis-pass")


def _load_redis_password() -> str | None:
    """
    Return the operator-managed Redis password, or None if not set.

    The installer writes ``/etc/hop3/redis-pass`` with mode 0640
    root:hop3; reading it requires being in the hop3 group, which the
    server process is. Any IO error → None (legacy unauth fall-back).
    """
    try:
        text = REDIS_PASS_FILE.read_text().strip()
    except OSError:
        return None
    return text or None


def _redis_cli_env() -> dict[str, str]:
    """
    Environment for invoking ``redis-cli`` so the password isn't on argv.

    ``REDISCLI_AUTH`` is the documented mechanism for passing the
    password without ``-a <password>`` (which would land in
    /proc/<pid>/cmdline).
    """
    import os  # ruff:ignore[import-outside-top-level]

    env = os.environ.copy()
    password = _load_redis_password()
    if password:
        env["REDISCLI_AUTH"] = password
    return env


def _run_redis_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run ``redis-cli`` with REDISCLI_AUTH injected when configured."""
    return subprocess.run(
        ["redis-cli", *args],
        capture_output=True,
        text=True,
        check=False,
        env=_redis_cli_env(),
    )


@dataclass(frozen=True)
class RedisAddon:
    """
    Redis service implementation using Addon protocol.

    This service provides Redis access to applications. Each addon instance
    uses a dedicated Redis database number for isolation.

    Attributes:
        addon_name: The unique name for this Redis service instance
        _db_number: The Redis database number (0-15) for this instance
    """

    # Class attribute for the strategy name
    name: str = "redis"

    # Instance attributes
    addon_name: str = ""
    # ``0`` is the sentinel for "not yet assigned" (db 0 is reserved and
    # never handed out to addons). The real assignment is loaded from the
    # secrets store in __post_init__, or allocated by ``create()``.
    _db_number: int = 0

    def __post_init__(self) -> None:
        """Validate addon_name and load any persisted db_number assignment."""
        if not self.addon_name:
            msg = "addon_name is required for RedisAddon"
            raise ValueError(msg)
        validate_service_name(self.addon_name)

        # If the addon already exists, its db_number lives in the secrets
        # file. Load it so subsequent operations (attach, info, destroy)
        # talk to the right db. New addons get a number allocated in
        # ``create()`` — we don't allocate here because instantiation is
        # also used for read-only operations.
        if self._db_number == 0:
            existing = load_addon_secrets(ADDON_TYPE, self.addon_name)
            if existing and isinstance(existing.get("db_number"), int):
                object.__setattr__(self, "_db_number", existing["db_number"])

    @property
    def db_number(self) -> int:
        """Get the Redis database number for this addon."""
        return self._db_number

    def _db_cmd(self, *args: str) -> subprocess.CompletedProcess[str]:
        """
        Run a redis-cli command scoped to this addon's database.

        Wraps ``-n <db_number>`` so the call sites read like Redis
        commands rather than argv soup.
        """
        return _run_redis_cli(["-n", str(self.db_number), *args])

    @property
    def instance_name(self) -> str:
        """Get a sanitized instance name."""
        return self.addon_name.replace("-", "_")

    def create(self) -> None:
        """
        Initialize the Redis database for this addon.

        Claims a free db number (1-15), persisting the claim before anything
        else so that two concurrent creates cannot be handed the same one.
        Verifies Redis is reachable and tags the db with a marker key.
        Existing addons (re-create after a partial install) keep their
        previously-assigned number.

        A failure after the claim releases it: fifteen slots is few enough
        that a lost one matters, and an addon that does not exist must not
        hold one.
        """
        # Claim on first create. If __post_init__ already loaded a number
        # from secrets (re-create after a partial install), keep it — and
        # leave it alone on failure, since this call did not claim it.
        claimed = self._db_number == 0
        if claimed:
            # frozen=True dataclass; object.__setattr__ is the standard pattern.
            object.__setattr__(  # ruff:ignore[unnecessary-dunder-call]
                self, "_db_number", _claim_db_number(self.addon_name)
            )

        try:
            self._initialize_database()
        except Exception:
            if claimed:
                _release_db_number(self.addon_name)
                object.__setattr__(self, "_db_number", 0)  # ruff:ignore[unnecessary-dunder-call]
            raise

    def _initialize_database(self) -> None:
        """Check Redis over, tag this addon's db, and record the assignment."""
        # Verify Redis is accessible
        result = _run_redis_cli(["ping"])
        if result.returncode != 0 or result.stdout.strip() != "PONG":
            msg = f"Redis is not accessible: {result.stderr or 'no response'}"
            raise RuntimeError(msg)

        # Ensure Redis is configured as a primary (not a read-only replica)
        # This fixes "You can't write against a read only replica" errors
        self._ensure_writable()

        # Select the database and set a marker key to indicate it's in use
        result = self._db_cmd(
            "SET",
            f"hop3:addon:{self.addon_name}:created",
            datetime.now(timezone.utc).isoformat(),
        )
        if result.returncode != 0:
            # Check if this is a read-only replica error
            if "read only replica" in result.stderr.lower():
                msg = (
                    "Redis is configured as a read-only replica. "
                    "Run 'redis-cli REPLICAOF NO ONE' to make it a primary, "
                    "or re-run the Hop3 installer with --features=redis"
                )
            else:
                msg = f"Failed to initialize Redis database: {result.stderr}"
            raise RuntimeError(msg)

        # Round out the claim with the creation timestamp. The db_number is
        # already on disk (that is what makes the claim a claim); this keeps
        # it and adds the rest of the record.
        save_addon_secrets(
            ADDON_TYPE,
            self.addon_name,
            {
                "db_number": self.db_number,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def _ensure_writable(self) -> None:
        """
        Ensure Redis is writable (not a read-only replica).

        If Redis is configured as a replica, attempt to make it a primary.
        """
        # Check if Redis is a replica
        result = _run_redis_cli(["INFO", "replication"])
        if result.returncode != 0:
            return  # Can't check, assume it's fine

        # Check if role is slave/replica
        if "role:slave" in result.stdout:
            # Try to make it a primary
            _run_redis_cli(["REPLICAOF", "NO", "ONE"])
            # Also allow writes on replica (fallback if REPLICAOF fails)
            _run_redis_cli(["CONFIG", "SET", "replica-read-only", "no"])

    def destroy(self) -> None:
        """
        Decommission this Redis addon.

        Flushes all keys in the assigned database and releases the
        db_number assignment so it can be reused by a future addon.
        """
        if self._db_number == 0:
            # Never had a number assigned (create() was not called or
            # the secrets file was already removed). Nothing to flush.
            delete_addon_secrets(ADDON_TYPE, self.addon_name)
            return

        result = self._db_cmd("FLUSHDB")
        if result.returncode != 0:
            msg = f"Failed to flush Redis database {self.db_number}: {result.stderr}"
            raise RuntimeError(msg)

        # Free the db_number for reuse.
        delete_addon_secrets(ADDON_TYPE, self.addon_name)

    def flush(self) -> None:
        """
        Remove all keys from this addon's Redis database (FLUSHDB).

        Unlike destroy(), the db_number assignment is kept — the addon stays
        usable, just emptied.
        """
        if self._db_number == 0:
            msg = f"Redis addon '{self.addon_name}' has no database assigned yet."
            raise RuntimeError(msg)
        result = self._db_cmd("FLUSHDB")
        if result.returncode != 0:
            msg = f"Failed to flush Redis database {self.db_number}: {result.stderr}"
            raise RuntimeError(msg)

    def run_command(self, command: str) -> str:
        """
        Run an ad-hoc redis-cli command scoped to this addon's database.

        The command is split with shlex and run via redis-cli (so it targets
        this addon's db number, not db 0). Returns the command's stdout.
        """
        if self._db_number == 0:
            msg = f"Redis addon '{self.addon_name}' has no database assigned yet."
            raise RuntimeError(msg)
        result = self._db_cmd(*shlex.split(command))
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "redis-cli command failed")
        return result.stdout.strip()

    def get_connection_details(self) -> dict[str, str]:
        """
        Get environment variables for connecting to this Redis instance.

        Returns:
            Dictionary with REDIS_URL and other connection parameters

        Note: This always returns 127.0.0.1 as the host (not "localhost") to
        avoid IPv6 resolution issues. For Docker deployments, the Docker deployer
        transforms 127.0.0.1 → host.docker.internal when generating
        docker-compose.yml.
        """
        # Always use 127.0.0.1 instead of "localhost" to avoid IPv6 resolution
        # issues (some runtimes resolve localhost to ::1 first, but Redis
        # typically only listens on 127.0.0.1).
        # Docker deployer transforms 127.0.0.1 → host.docker.internal for containers.
        host = "127.0.0.1"
        port = "6379"
        password = _load_redis_password()

        # When auth is configured, surface the password in REDIS_URL (the
        # standard form ``redis://:<password>@host:port/db``) and also
        # via REDIS_PASSWORD for libraries that read it separately.
        # Quote the password since token_urlsafe can include "-" / "_"
        # but not "@" / ":" / "/", so naive interpolation is safe; we
        # still pass it through quote() defensively in case the operator
        # rotates to a custom value.
        if password:
            from urllib.parse import quote  # ruff:ignore[import-outside-top-level]

            url = f"redis://:{quote(password, safe='')}@{host}:{port}/{self.db_number}"
        else:
            url = f"redis://{host}:{port}/{self.db_number}"

        details = {
            "REDIS_URL": url,
            "REDIS_HOST": host,
            "REDIS_PORT": port,
            "REDIS_DB": str(self.db_number),
        }
        if password:
            details["REDIS_PASSWORD"] = password
        return details

    def backup(self) -> Path:
        """
        Create a backup of the Redis database.

        Uses redis-cli to dump all keys in this database.

        Returns:
            Path to the backup file
        """
        backup_dir = HOP3_ROOT / "backups" / "redis"
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"{self.addon_name}_{timestamp}.json"

        # Get all keys in this database
        result = self._db_cmd("KEYS", "*")
        if result.returncode != 0:
            msg = f"Failed to list Redis keys: {result.stderr}"
            raise RuntimeError(msg)

        keys = result.stdout.strip().split("\n") if result.stdout.strip() else []

        # Dump each key with its type and value
        keys_data: dict[str, dict[str, Any]] = {}
        backup_data: dict[str, Any] = {
            "addon_name": self.addon_name,
            "db_number": self.db_number,
            "timestamp": timestamp,
            "keys": keys_data,
        }

        for key in keys:
            if not key:
                continue

            # Get key type
            key_type = self._db_cmd("TYPE", key).stdout.strip()

            # Get value based on type
            if key_type == "string":
                value_result = self._db_cmd("GET", key)
                keys_data[key] = {
                    "type": "string",
                    "value": value_result.stdout.strip(),
                }
            elif key_type == "list":
                value_result = self._db_cmd("LRANGE", key, "0", "-1")
                keys_data[key] = {
                    "type": "list",
                    "value": value_result.stdout.strip().split("\n"),
                }
            elif key_type == "set":
                value_result = self._db_cmd("SMEMBERS", key)
                keys_data[key] = {
                    "type": "set",
                    "value": value_result.stdout.strip().split("\n"),
                }
            elif key_type == "hash":
                value_result = self._db_cmd("HGETALL", key)
                # Parse alternating key/value pairs
                items = value_result.stdout.strip().split("\n")
                hash_dict = {}
                for i in range(0, len(items) - 1, 2):
                    hash_dict[items[i]] = items[i + 1]
                keys_data[key] = {"type": "hash", "value": hash_dict}
            # Skip other types for now (zset, stream, etc.)

        # Write backup to file
        with Path(backup_file).open("w") as f:
            json.dump(backup_data, f, indent=2)

        return backup_file

    def restore(self, backup_path: Path) -> None:
        """
        Restore Redis database from a backup file.

        Args:
            backup_path: Path to the JSON backup file
        """
        # Confine the caller-supplied path to the backup tree: this value
        # comes straight from RPC and reaches a file-reading sink below.
        # Same root backup() writes to, so the two cannot drift apart.
        backup_path = resolve_backup_file(backup_path, HOP3_ROOT / "backups")

        with Path(backup_path).open() as f:
            backup_data = json.load(f)

        # Restore each key based on its type
        for key, data in backup_data.get("keys", {}).items():
            key_type = data["type"]
            value = data["value"]

            if key_type == "string":
                self._db_cmd("SET", key, str(value))
            elif key_type == "list":
                # Delete existing key first
                self._db_cmd("DEL", key)
                for item in value:
                    self._db_cmd("RPUSH", key, str(item))
            elif key_type == "set":
                self._db_cmd("DEL", key)
                for item in value:
                    self._db_cmd("SADD", key, str(item))
            elif key_type == "hash":
                self._db_cmd("DEL", key)
                for field, val in value.items():
                    self._db_cmd("HSET", key, field, str(val))

    def info(self) -> dict[str, Any]:
        """
        Get information about the Redis service.

        Returns:
            Dictionary with service details
        """
        # Get Redis server info
        result = _run_redis_cli(["INFO", "server"])

        version = "unknown"
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                if line.startswith("redis_version:"):
                    version = line.split(":")[1].strip()
                    break

        # Get number of keys in this database
        dbsize_result = self._db_cmd("DBSIZE")
        key_count = 0
        if dbsize_result.returncode == 0:
            # Output format: "(integer) N"
            with contextlib.suppress(ValueError, IndexError):
                key_count = int(dbsize_result.stdout.strip())

        # Get memory usage for this database (approximate)
        memory_result = self._db_cmd("INFO", "memory")
        used_memory = "unknown"
        if memory_result.returncode == 0:
            for line in memory_result.stdout.split("\n"):
                if line.startswith("used_memory_human:"):
                    used_memory = line.split(":")[1].strip()
                    break

        return {
            "addon_name": self.addon_name,
            "type": "redis",
            "host": "127.0.0.1",
            "port": 6379,
            "database": self.db_number,
            "key_count": key_count,
            "version": version,
            "memory_used": used_memory,
        }


@contextlib.contextmanager
def _db_number_lock() -> Iterator[None]:
    """
    Hold the lock that makes a db-number claim atomic.

    Allocation is a read-modify-write over the addon-secrets directory, so
    two of them interleaving hand out the same number. The exclusion has to
    be filesystem-level rather than a ``threading.Lock``: a CLI-side addon
    command and the server are different processes over the same directory.

    Blocking, not ``LOCK_NB``: two creates racing should queue behind each
    other, and the critical section is one directory scan.
    """
    secrets_dir = HOP3_ROOT / "addons" / ADDON_TYPE
    secrets_dir.mkdir(parents=True, exist_ok=True)
    fd = os.open(secrets_dir / DB_NUMBER_LOCK_FILE, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _db_number_owners() -> dict[int, str]:
    """
    Map each assigned db number to the addon holding it.

    Files that don't parse or don't carry a ``db_number`` are skipped: a
    corrupt secrets file should not block allocation. It does mean such a
    file's number can be handed out twice, which is why a claim is written
    under the lock and never inferred later.
    """
    owners: dict[int, str] = {}
    secrets_dir = HOP3_ROOT / "addons" / ADDON_TYPE
    if not secrets_dir.exists():
        return owners
    for secrets_file in secrets_dir.glob("*.json"):
        try:
            with secrets_file.open() as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        n = data.get("db_number")
        if isinstance(n, int) and MIN_ADDON_DB <= n <= MAX_ADDON_DB:
            owners[n] = secrets_file.stem
    return owners


def _claim_db_number(addon_name: str) -> int:
    """
    Reserve the lowest free db number for ``addon_name`` and persist it now.

    Choosing and recording happen under one lock. They used to be minutes
    apart — the number was picked, then Redis was pinged, made writable and
    given a marker key, and only then was the assignment saved — so two
    ``addon create`` calls passing through that window both picked the same
    number and silently shared a database with each other's keys.

    Raises:
        RuntimeError: every db in [MIN_ADDON_DB, MAX_ADDON_DB] is taken.
    """
    with _db_number_lock():
        owners = _db_number_owners()
        for n in range(MIN_ADDON_DB, MAX_ADDON_DB + 1):
            if n in owners:
                continue
            secrets = load_addon_secrets(ADDON_TYPE, addon_name) or {}
            secrets["db_number"] = n
            save_addon_secrets(ADDON_TYPE, addon_name, secrets)
            return n

        holders = ", ".join(f"{n} → {owners[n]}" for n in sorted(owners))
        msg = (
            f"Redis addon '{addon_name}' can't be created: all databases "
            f"({MIN_ADDON_DB}-{MAX_ADDON_DB}) are in use. Redis ships with 16 "
            f"logical dbs and Hop3 reserves db 0. In use: {holders}. Destroy an "
            f"unused redis addon (`hop3 addon redis destroy <name>`) first."
        )
        raise RuntimeError(msg)


def _release_db_number(addon_name: str) -> None:
    """
    Give a claimed db number back.

    Called when a create fails after claiming: a slot held by an addon that
    does not exist is a slot lost until someone reads the secrets directory
    by hand, and there are only fifteen of them.
    """
    with _db_number_lock():
        secrets = load_addon_secrets(ADDON_TYPE, addon_name) or {}
        secrets.pop("db_number", None)
        if secrets:
            save_addon_secrets(ADDON_TYPE, addon_name, secrets)
        else:
            delete_addon_secrets(ADDON_TYPE, addon_name)
