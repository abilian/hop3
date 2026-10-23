# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
S3-compatible object storage addon for Hop3.

Each ``addons create s3 <name>`` provisions:

- A dedicated bucket (named ``hop3-<addon_name>``)
- A per-addon access key/secret pair scoped to that bucket
- An entry in the addon credentials DB (credentials at rest encrypted
  by the same Fernet key used for PostgreSQL addon passwords)

The addon injects ``S3_*`` env vars into attached apps. See
``backend.py`` for the backend abstraction (default: Garage) and
``s3api.py`` for the object operations backup and restore use.
"""

from __future__ import annotations

import contextlib
import json
import shutil
import tarfile
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from hop3.config import HopConfig
from hop3.core.backup import resolve_backup_file

from .backend import BackendError, S3Credentials, get_default_backend
from .s3api import DEFAULT_CONTENT_TYPE, S3Client

if TYPE_CHECKING:
    from pathlib import Path

    from .backend import S3Backend


def _hop3_root() -> Path:
    """
    Resolve HOP3_ROOT lazily via the config singleton.

    This indirection is required so tests that override the singleton
    see the new value (module-level imports would freeze the path at
    import time).
    """
    return HopConfig.get_instance().HOP3_ROOT


@dataclass(frozen=True)
class S3Addon:
    """
    S3 object storage addon implementing the Addon protocol.

    One instance per ``addons create s3 <name>`` call. The addon
    delegates all S3 server interaction to the configured backend
    (see :func:`backend.get_default_backend`).
    """

    # Class attribute for the strategy name
    name: str = "s3"

    # Instance attributes
    addon_name: str = ""

    # Resolved at init time; tests can pass a stub instead.
    backend: S3Backend = field(default_factory=get_default_backend, repr=False)

    def __post_init__(self) -> None:
        if not self.addon_name:
            msg = "addon_name is required for S3Addon"
            raise ValueError(msg)

    @property
    def bucket_name(self) -> str:
        """
        Bucket name derived from the addon name.

        Uses a ``hop3-`` prefix so ``list_buckets`` can filter
        Hop3-managed buckets from any others on the server.
        """
        return f"hop3-{self.addon_name}"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def create(self) -> None:
        """
        Provision the bucket and create a scoped access key.

        Stores the generated credentials in the addon credentials file
        at ``HOP3_ROOT/addons/s3/<addon_name>.json`` (encrypted at rest
        by the same mechanism as other addon credentials in 0.6).
        """
        self.backend.create_bucket(self.bucket_name)
        credentials = self.backend.create_access_key(self.bucket_name)
        self._save_credentials(credentials)

    def destroy(self) -> None:
        """
        Destroy the bucket, access key, and stored credentials.

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
        """
        Return env vars for an attached app.

        The app reads these from its runtime environment. All major
        S3 SDKs understand these variable names directly (AWS SDK,
        boto3, minio client, s3cmd, ...).
        """
        credentials = self._require_credentials()
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
        """
        Archive every object in the bucket, with its content type, as a tar.

        Read with the app's own key, which reaches this bucket and no other.
        Each object goes through a temporary file, never held in memory.
        """
        client = self._client()
        backup_dir = _hop3_root() / "backups" / "s3"
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"{self.addon_name}_{timestamp}.tar"

        try:
            with tarfile.open(backup_file, "w", format=tarfile.PAX_FORMAT) as tar:
                for key in client.list_keys(self.bucket_name):
                    with tempfile.TemporaryFile() as body:
                        content_type = client.download(self.bucket_name, key, body)
                        member = tarfile.TarInfo(key)
                        member.size = body.tell()
                        member.mtime = int(time.time())
                        member.pax_headers = {_CONTENT_TYPE_PAX: content_type}
                        body.seek(0)
                        tar.addfile(member, body)
        except BaseException:
            backup_file.unlink(missing_ok=True)
            raise
        return backup_file

    def restore(self, backup_path: Path) -> None:
        """
        Replace the bucket's objects with the ones archived in ``backup_path``.

        The whole archive is read before the bucket is touched, so a backup
        that is not one is refused with the bucket as it was. Every archived
        object is then written, and only after that are the objects the backup
        does not hold deleted. A restore that fails part-way leaves the
        bucket's own objects plus part of the backup's, and can be run again.
        """
        backup_path = resolve_backup_file(backup_path, _hop3_root() / "backups")
        if not tarfile.is_tarfile(backup_path):
            msg = (
                f"{backup_path} is not an S3 object backup. One taken before "
                "Hop3 0.8 is a JSON manifest of the bucket's metadata and holds "
                "none of its objects, so it cannot put them back. Take a new "
                f"one with: hop3 addon s3 dump {self.addon_name}"
            )
            raise ValueError(msg)
        client = self._client()
        with tarfile.open(backup_path, "r:") as tar:
            members = _object_members(tar, backup_path)
            for member in members:
                source = tar.extractfile(member)
                assert source is not None  # a regular file, checked above
                with tempfile.TemporaryFile() as body:
                    shutil.copyfileobj(source, body)
                    client.upload(
                        self.bucket_name,
                        member.name,
                        body,
                        member.pax_headers.get(_CONTENT_TYPE_PAX, DEFAULT_CONTENT_TYPE),
                    )
        restored = {member.name for member in members}
        for key in list(client.list_keys(self.bucket_name)):
            if key not in restored:
                client.delete(self.bucket_name, key)

    def _client(self) -> S3Client:
        """An S3 client holding the app's own key to the bucket."""
        credentials = self._require_credentials()
        return S3Client(
            endpoint=credentials.endpoint,
            region=credentials.region,
            access_key=credentials.access_key,
            secret_key=credentials.secret_key,
        )

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    def info(self) -> dict[str, Any]:
        """Return current status for `hop3 addon info`."""
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
        """
        Persist credentials to disk.

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

    def _require_credentials(self) -> S3Credentials:
        credentials = self._load_credentials()
        if credentials is None:
            msg = (
                f"No credentials found for S3 addon {self.addon_name!r}. "
                "Was it created? Run: hop3 addon create s3 <name>"
            )
            raise RuntimeError(msg)
        return credentials

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


#: The PAX header an archived object's content type travels in.
_CONTENT_TYPE_PAX = "HOP3.content-type"


def _object_members(tar: tarfile.TarFile, backup_path: Path) -> list[tarfile.TarInfo]:
    """
    The archive's objects, or a ValueError naming what else it holds.

    Checked before the bucket is touched, so a wrong archive changes nothing.
    """
    members = tar.getmembers()
    strays = [m.name for m in members if not m.isfile()]
    if strays:
        msg = (
            f"{backup_path} is not an S3 object backup: it holds "
            f"{', '.join(strays[:3])}, which are not objects."
        )
        raise ValueError(msg)
    return members
