# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Backend abstraction for S3-compatible object storage.

Hop3's S3 addon talks to an underlying object-storage server (MinIO,
Garage, SeaweedFS, ...) through the ``S3Backend`` protocol. Swapping
backends is done by registering a different implementation — no
changes to the addon class, CLI, or injected env vars.

The default implementation is ``MinIOBackend``, which shells out to
the ``mc`` admin CLI. A ``GarageBackend`` stub exists for the eventual
replacement (see licensing note in the package docstring).
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

__all__ = [
    "BackendError",
    "GarageBackend",
    "MinIOBackend",
    "S3Backend",
    "S3Credentials",
    "get_default_backend",
]


class BackendError(Exception):
    """Raised when the underlying S3 server refuses an operation."""


@dataclass(frozen=True)
class S3Credentials:
    """Access key/secret pair scoped to a single bucket.

    The ``endpoint`` is included so clients get everything they need
    to construct a connection in a single place.
    """

    access_key: str
    secret_key: str
    endpoint: str
    region: str = "us-east-1"


class S3Backend(Protocol):
    """Protocol for S3-compatible backend implementations.

    Backends must support per-bucket access keys so apps can't see
    each other's data. Backends that don't (e.g., single-shared-key
    MinIO setups) should raise ``BackendError`` from ``create_access_key``.
    """

    @property
    def name(self) -> str:
        """Backend type identifier, e.g., "minio", "garage"."""

    @property
    def endpoint(self) -> str:
        """Base URL of the backend server (e.g., "http://127.0.0.1:9000")."""

    def create_bucket(self, bucket: str) -> None:
        """Create a bucket. Idempotent: no error if it already exists."""

    def delete_bucket(self, bucket: str) -> None:
        """Delete a bucket and all its contents. Idempotent."""

    def create_access_key(self, bucket: str) -> S3Credentials:
        """Create an access key scoped to a single bucket.

        The returned credentials must only allow read/write to ``bucket``
        and nothing else.
        """

    def delete_access_key(self, access_key: str) -> None:
        """Delete an access key. Idempotent."""

    def list_buckets(self) -> list[str]:
        """List all buckets managed by Hop3 (prefix-filtered)."""

    def bucket_info(self, bucket: str) -> dict[str, str]:
        """Return metadata about a bucket (size, object count, ...)."""


# ---------------------------------------------------------------------------
# MinIO implementation (default for now — see licensing note in __init__.py)
# ---------------------------------------------------------------------------


#: File where the installer writes ``MC_HOST_hop3=<credentials-url>``.
#: The hop3 user can read this file (0640 root:hop3) and use its
#: contents to drive ``mc`` without needing an alias in its home dir.
HOP3_S3_ENV_FILE = "/etc/hop3/s3-env"


def _load_mc_host_env() -> dict[str, str]:
    """Return env vars for ``mc`` subprocess calls.

    Reads ``/etc/hop3/s3-env`` (written by the installer) and parses
    out the ``MC_HOST_hop3`` line. Returns an empty dict if the file
    doesn't exist — in that case ``mc`` will fall back to whatever
    alias config is in ``~/.mc/config.json`` (useful for dev setups
    where the user runs ``mc alias set`` manually).
    """
    env_file = Path(HOP3_S3_ENV_FILE)
    if not env_file.exists():
        return {}
    try:
        content = env_file.read_text()
    except OSError:
        return {}
    out: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


@dataclass(frozen=True)
class MinIOBackend:
    """MinIO backend driven through the ``mc`` admin CLI.

    Assumes ``mc`` is installed on the server and an alias named
    ``hop3`` points to the local MinIO instance with admin credentials.
    Credentials are read from ``/etc/hop3/s3-env`` (written by the
    installer) and passed to ``mc`` via ``MC_HOST_hop3``.
    """

    name: str = "minio"
    endpoint: str = "http://127.0.0.1:9000"
    mc_alias: str = "hop3"

    def _mc(self, *args: str) -> subprocess.CompletedProcess[str]:
        """Run ``mc <args>`` and return the result.

        Injects ``MC_HOST_hop3`` from ``/etc/hop3/s3-env`` into the
        subprocess environment so ``mc`` can authenticate without a
        per-user config file. Raises ``BackendError`` on non-zero exit
        (or if the credentials file is missing).
        """
        cmd = ["mc", "--json", *args]
        mc_env = _load_mc_host_env()
        # Credentials must come from either the env file (installer)
        # or the caller's own environment (dev setups). If neither is
        # present, give a concrete error rather than letting mc fail
        # with "No valid configuration found for 'hop3' host alias".
        # MinIO's mc uses the lowercase alias name in MC_HOST_<alias>
        # env vars. This is the vendor's chosen convention; don't
        # uppercase it.
        if not mc_env and not os.environ.get("MC_HOST_hop3"):  # noqa: SIM112
            msg = (
                f"MinIO backend credentials not found. Expected "
                f"{HOP3_S3_ENV_FILE} to contain MC_HOST_hop3=... "
                f"Was the server installed with '--with s3'?"
            )
            raise BackendError(msg)
        subprocess_env = os.environ.copy()
        subprocess_env.update(mc_env)
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=False, env=subprocess_env
        )
        if result.returncode != 0:
            msg = f"mc {' '.join(args)} failed: {result.stderr or result.stdout}"
            raise BackendError(msg)
        return result

    def create_bucket(self, bucket: str) -> None:
        target = f"{self.mc_alias}/{bucket}"
        # mc mb is idempotent with --ignore-existing
        self._mc("mb", "--ignore-existing", target)

    def delete_bucket(self, bucket: str) -> None:
        target = f"{self.mc_alias}/{bucket}"
        # Remove all objects first (mc rb refuses non-empty buckets).
        # Bucket may already be empty or not exist — continue regardless.
        with contextlib.suppress(BackendError):
            self._mc("rm", "--recursive", "--force", target)
        try:
            self._mc("rb", "--force", target)
        except BackendError as e:
            # Idempotent: don't fail if already gone
            if "does not exist" not in str(e).lower():
                raise

    def create_access_key(self, bucket: str) -> S3Credentials:
        """Create a user and access key scoped to the bucket.

        Creates a MinIO user with a policy restricting access to the
        named bucket only, then returns the generated access/secret
        key pair.
        """
        # Generate user credentials
        access_key = f"hop3-{bucket}-{secrets.token_hex(4)}"
        secret_key = secrets.token_urlsafe(32)

        # Create the user
        self._mc(
            "admin",
            "user",
            "add",
            self.mc_alias,
            access_key,
            secret_key,
        )

        # Attach a policy that only allows access to the named bucket.
        # MinIO's "readwrite" built-in policy is too broad; we need a
        # scoped inline policy instead.
        policy_json = (
            '{"Version":"2012-10-17","Statement":[{'
            '"Effect":"Allow",'
            '"Action":["s3:*"],'
            f'"Resource":["arn:aws:s3:::{bucket}","arn:aws:s3:::{bucket}/*"]'
            "}]}"
        )
        policy_name = f"hop3-{bucket}"

        # Write policy to a temp file (mc expects a path, not inline JSON)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(policy_json)
            policy_path = f.name

        try:
            self._mc(
                "admin", "policy", "create", self.mc_alias, policy_name, policy_path
            )
            self._mc(
                "admin",
                "policy",
                "attach",
                self.mc_alias,
                policy_name,
                "--user",
                access_key,
            )
        finally:
            Path(policy_path).unlink(missing_ok=True)

        return S3Credentials(
            access_key=access_key,
            secret_key=secret_key,
            endpoint=self.endpoint,
        )

    def delete_access_key(self, access_key: str) -> None:
        try:
            self._mc("admin", "user", "remove", self.mc_alias, access_key)
        except BackendError as e:
            if "does not exist" not in str(e).lower():
                raise

    def list_buckets(self) -> list[str]:
        result = self._mc("ls", self.mc_alias)
        # Each line is a separate JSON object from `mc --json`.
        buckets: list[str] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = entry.get("key", "")
            # mc ls appends "/" to bucket names
            if key.endswith("/"):
                buckets.append(key.rstrip("/"))
        return buckets

    def bucket_info(self, bucket: str) -> dict[str, str]:
        target = f"{self.mc_alias}/{bucket}"
        try:
            result = self._mc("du", target)
        except BackendError as e:
            return {"error": str(e)}
        # Parse the last JSON line for the total
        for line in reversed(result.stdout.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                return {
                    "size": str(entry.get("size", "unknown")),
                    "objects": str(entry.get("objects", "unknown")),
                }
            except json.JSONDecodeError:
                continue
        return {}


# ---------------------------------------------------------------------------
# Garage implementation (stub — see licensing note in __init__.py)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GarageBackend:
    """Garage backend — NOT IMPLEMENTED YET.

    Garage is the planned replacement for MinIO: genuinely AGPL, single
    Rust binary, designed for self-hosting at edge. See
    https://garagehq.deuxfleurs.fr/.

    Garage's admin API is JSON-RPC over HTTP (not a CLI). The
    implementation will be similar in shape to ``MinIOBackend`` but
    uses ``httpx.post(admin_endpoint, json=...)`` instead of shelling
    out to ``mc``.
    """

    name: str = "garage"
    endpoint: str = "http://127.0.0.1:3900"
    admin_endpoint: str = "http://127.0.0.1:3903"
    admin_token: str = ""

    def create_bucket(self, bucket: str) -> None:
        msg = "GarageBackend is not implemented yet — use MinIOBackend"
        raise NotImplementedError(msg)

    def delete_bucket(self, bucket: str) -> None:
        raise NotImplementedError

    def create_access_key(self, bucket: str) -> S3Credentials:
        raise NotImplementedError

    def delete_access_key(self, access_key: str) -> None:
        raise NotImplementedError

    def list_buckets(self) -> list[str]:
        raise NotImplementedError

    def bucket_info(self, bucket: str) -> dict[str, str]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------


def get_default_backend() -> S3Backend:
    """Return the default S3 backend for this server.

    Selection is driven by the ``HOP3_S3_BACKEND`` env var:
      - ``"minio"`` (default): shell out to ``mc``
      - ``"garage"``: JSON-RPC to the Garage admin API (not implemented)

    The choice is server-wide: a single Hop3 server uses one backend.
    """
    choice = os.environ.get("HOP3_S3_BACKEND", "minio").lower()
    if choice == "minio":
        return MinIOBackend()
    if choice == "garage":
        return GarageBackend()
    msg = f"Unknown HOP3_S3_BACKEND: {choice!r}"
    raise ValueError(msg)
