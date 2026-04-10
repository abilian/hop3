# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""S3-compatible object storage addon for Hop3.

Each ``addons:create s3 <name>`` provisions:

- A dedicated bucket (named ``hop3-<addon_name>``)
- A per-addon access key/secret pair scoped to that bucket
- An entry in the addon credentials DB (credentials at rest encrypted
  by the same Fernet key used for PostgreSQL addon passwords)

The addon injects ``S3_*`` env vars into attached apps. See
``backend.py`` for the backend abstraction (default: MinIO, planned
replacement: Garage).
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from hop3.config import HopConfig

from .backend import BackendError, S3Credentials, get_default_backend

if TYPE_CHECKING:
    from pathlib import Path

    from .backend import S3Backend


def _hop3_root() -> Path:
    """Resolve HOP3_ROOT lazily via the config singleton.

    This indirection is required so tests that override the singleton
    see the new value (module-level imports would freeze the path at
    import time).
    """
    return HopConfig.get_instance().HOP3_ROOT


@dataclass(frozen=True)
class S3Addon:
    """S3 object storage addon implementing the Addon protocol.

    One instance per ``addons:create s3 <name>`` call. The addon
    delegates all S3 server interaction to the configured backend
    (see :func:`backend.get_default_backend`).
    """

    # Class attribute for the strategy name
    name: str = "s3"

    # Instance attributes
    addon_name: str = ""

    # Resolved in __post_init__. Tests can pass a stub via the
    # default argument; production callers leave it None and the
    # default backend is resolved at init time.
    backend: S3Backend = field(default=None, repr=False)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if not self.addon_name:
            msg = "addon_name is required for S3Addon"
            raise ValueError(msg)
        # Resolve the default backend if none was injected.
        if self.backend is None:
            object.__setattr__(self, "backend", get_default_backend())

    @property
    def bucket_name(self) -> str:
        """Bucket name derived from the addon name.

        Uses a ``hop3-`` prefix so ``list_buckets`` can filter
        Hop3-managed buckets from any others on the server.
        """
        return f"hop3-{self.addon_name}"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def create(self) -> None:
        """Provision the bucket and create a scoped access key.

        Stores the generated credentials in the addon credentials file
        at ``HOP3_ROOT/addons/s3/<addon_name>.json`` (encrypted at rest
        by the same mechanism as other addon credentials in 0.6).
        """
        self.backend.create_bucket(self.bucket_name)
        credentials = self.backend.create_access_key(self.bucket_name)
        self._save_credentials(credentials)

    def destroy(self) -> None:
        """Destroy the bucket, access key, and stored credentials.

        Idempotent: no error if the resources don't exist. Continues
        cleanup even if individual steps fail — the goal is to leave
        as little residue as possible.
        """
        credentials = self._load_credentials()
        if credentials:
            with contextlib.suppress(BackendError):
                self.backend.delete_access_key(credentials.access_key)
        with contextlib.suppress(BackendError):
            self.backend.delete_bucket(self.bucket_name)
        self._delete_credentials()

    # ------------------------------------------------------------------
    # Connection details (env var injection)
    # ------------------------------------------------------------------

    def get_connection_details(self) -> dict[str, str]:
        """Return env vars for an attached app.

        The app reads these from its runtime environment. All major
        S3 SDKs understand these variable names directly (AWS SDK,
        boto3, minio client, s3cmd, ...).
        """
        credentials = self._load_credentials()
        if credentials is None:
            msg = (
                f"No credentials found for S3 addon {self.addon_name!r}. "
                "Was it created? Run: hop3 addons:create s3 <name>"
            )
            raise RuntimeError(msg)

        return {
            "S3_ENDPOINT": credentials.endpoint,
            "S3_BUCKET": self.bucket_name,
            "S3_ACCESS_KEY": credentials.access_key,
            "S3_SECRET_KEY": credentials.secret_key,
            "S3_REGION": credentials.region,
            "S3_USE_PATH_STYLE": "true",
            # Also set AWS_* aliases for SDKs that prefer them
            "AWS_ENDPOINT_URL": credentials.endpoint,
            "AWS_ACCESS_KEY_ID": credentials.access_key,
            "AWS_SECRET_ACCESS_KEY": credentials.secret_key,
            "AWS_REGION": credentials.region,
        }

    # ------------------------------------------------------------------
    # Backup / restore
    # ------------------------------------------------------------------

    def backup(self) -> Path:
        """Create a backup of the S3 bucket contents.

        For now this writes a manifest (credentials + bucket metadata)
        and logs the bucket name. Full object-level backup via
        ``mc mirror`` is deferred to 0.6 (needs a target path and
        retention policy decisions).
        """
        backup_dir = _hop3_root() / "backups" / "s3"
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"{self.addon_name}_{timestamp}.json"

        credentials = self._load_credentials()
        info = self.backend.bucket_info(self.bucket_name)

        backup_data = {
            "addon_name": self.addon_name,
            "bucket": self.bucket_name,
            "timestamp": timestamp,
            "backend": self.backend.name,
            "endpoint": self.backend.endpoint,
            "credentials": {
                "access_key": credentials.access_key if credentials else None,
                # Secret key intentionally omitted from backup manifest
            },
            "info": info,
        }

        backup_file.write_text(json.dumps(backup_data, indent=2))
        return backup_file

    def restore(self, backup_path: Path) -> None:
        """Restore S3 addon metadata from a backup manifest.

        This only restores the credentials and bucket metadata, not
        the objects themselves. Full object restore is 0.6 work.
        """
        if not backup_path.exists():
            msg = f"Backup file not found: {backup_path}"
            raise FileNotFoundError(msg)

        data = json.loads(backup_path.read_text())
        # At this stage we don't re-provision the bucket from a backup;
        # the admin is expected to run `addons:create` first.
        # This method is a placeholder for the 0.6 mirror-restore.
        del data  # unused

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    def info(self) -> dict[str, Any]:
        """Return current status for `hop3 addons:info`."""
        try:
            bucket_info = self.backend.bucket_info(self.bucket_name)
        except BackendError as e:
            bucket_info = {"error": str(e)}

        credentials = self._load_credentials()

        return {
            "addon_name": self.addon_name,
            "type": "s3",
            "backend": self.backend.name,
            "endpoint": self.backend.endpoint,
            "bucket": self.bucket_name,
            "has_credentials": credentials is not None,
            "bucket_info": bucket_info,
        }

    # ------------------------------------------------------------------
    # Internal: credentials persistence
    # ------------------------------------------------------------------

    @property
    def _credentials_path(self) -> Path:
        return _hop3_root() / "addons" / "s3" / f"{self.addon_name}.json"

    def _save_credentials(self, credentials: S3Credentials) -> None:
        """Persist credentials to disk.

        Uses 0600 permissions. Proper encryption-at-rest will come
        when we unify with the existing ``AddonCredential`` ORM model
        (same Fernet key used for Postgres passwords).
        """
        path = self._credentials_path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "access_key": credentials.access_key,
            "secret_key": credentials.secret_key,
            "endpoint": credentials.endpoint,
            "region": credentials.region,
        }
        path.write_text(json.dumps(payload, indent=2))
        path.chmod(0o600)

    def _load_credentials(self) -> S3Credentials | None:
        path = self._credentials_path
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return S3Credentials(
            access_key=data["access_key"],
            secret_key=data["secret_key"],
            endpoint=data["endpoint"],
            region=data.get("region", "us-east-1"),
        )

    def _delete_credentials(self) -> None:
        path = self._credentials_path
        path.unlink(missing_ok=True)
