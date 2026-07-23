# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Tests for the S3Addon class.

Uses a stub backend to avoid needing a real MinIO/Garage server.
The backend protocol is the right unit of isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from hop3.plugins.s3.backend import BackendError, S3Credentials
from hop3.plugins.s3.s3 import S3Addon


@dataclass
class StubBackend:
    """In-memory backend for unit tests."""

    name: str = "stub"
    endpoint: str = "http://stub.test:9000"
    buckets: set[str] = field(default_factory=set)
    access_keys: dict[str, str] = field(default_factory=dict)  # access_key → bucket
    fail_next: str | None = None  # simulate a backend error on the next op

    def _maybe_fail(self, op: str) -> None:
        if self.fail_next == op:
            self.fail_next = None
            msg = f"simulated failure in {op}"
            raise BackendError(msg)

    def create_bucket(self, bucket: str) -> None:
        self._maybe_fail("create_bucket")
        self.buckets.add(bucket)

    def delete_bucket(self, bucket: str) -> None:
        self._maybe_fail("delete_bucket")
        self.buckets.discard(bucket)

    def create_access_key(self, bucket: str) -> S3Credentials:
        self._maybe_fail("create_access_key")
        access_key = f"stub-{bucket}"
        secret_key = f"secret-for-{bucket}"
        self.access_keys[access_key] = bucket
        return S3Credentials(
            access_key=access_key,
            secret_key=secret_key,
            endpoint=self.endpoint,
        )

    def delete_access_key(self, access_key: str) -> None:
        self._maybe_fail("delete_access_key")
        self.access_keys.pop(access_key, None)

    def list_buckets(self) -> list[str]:
        return sorted(self.buckets)

    def bucket_info(self, bucket: str) -> dict[str, str]:
        if bucket not in self.buckets:
            return {"error": "does not exist"}
        return {"size": "0", "objects": "0"}


@pytest.fixture
def hop3_root(tmp_path, monkeypatch):
    """Redirect HOP3_ROOT to a temp dir so tests don't touch real filesystem."""
    monkeypatch.setenv("HOP3_ROOT", str(tmp_path))
    # Reset the singleton so it picks up the new env var
    from hop3.config import HopConfig  # ruff:ignore[import-outside-top-level]

    HopConfig.reset_instance()
    yield tmp_path
    HopConfig.reset_instance()


@pytest.fixture
def backend():
    return StubBackend()


def test_addon_name_required():
    with pytest.raises(ValueError, match="addon_name is required"):
        S3Addon(addon_name="")


def test_bucket_name_uses_prefix(backend):
    addon = S3Addon(addon_name="myapp", backend=backend)
    assert addon.bucket_name == "hop3-myapp"


def test_create_provisions_bucket_and_credentials(hop3_root, backend):
    addon = S3Addon(addon_name="myapp", backend=backend)
    addon.create()

    assert "hop3-myapp" in backend.buckets
    assert "stub-hop3-myapp" in backend.access_keys
    # Credentials file written to disk
    assert (hop3_root / "addons" / "s3" / "myapp.json").exists()


def test_get_connection_details_returns_env_vars(hop3_root, backend):
    addon = S3Addon(addon_name="myapp", backend=backend)
    addon.create()

    env = addon.get_connection_details()
    assert env["S3_BUCKET"] == "hop3-myapp"
    assert env["S3_ACCESS_KEY"] == "stub-hop3-myapp"
    assert env["S3_SECRET_KEY"] == "secret-for-hop3-myapp"
    assert env["S3_ENDPOINT"] == "http://stub.test:9000"
    assert env["S3_USE_PATH_STYLE"] == "true"
    # AWS aliases should match the S3_* values
    assert env["AWS_ACCESS_KEY_ID"] == env["S3_ACCESS_KEY"]
    assert env["AWS_SECRET_ACCESS_KEY"] == env["S3_SECRET_KEY"]
    assert env["AWS_ENDPOINT_URL"] == env["S3_ENDPOINT"]


def test_get_connection_details_raises_before_create(hop3_root, backend):
    addon = S3Addon(addon_name="myapp", backend=backend)
    with pytest.raises(RuntimeError, match="No credentials found"):
        addon.get_connection_details()


def test_destroy_removes_everything(hop3_root, backend):
    addon = S3Addon(addon_name="myapp", backend=backend)
    addon.create()
    assert backend.buckets
    assert backend.access_keys

    addon.destroy()
    assert "hop3-myapp" not in backend.buckets
    assert not backend.access_keys
    assert not (hop3_root / "addons" / "s3" / "myapp.json").exists()


def test_destroy_is_idempotent(hop3_root, backend):
    """Destroy a never-created addon should not raise."""
    addon = S3Addon(addon_name="ghost", backend=backend)
    # Should not raise
    addon.destroy()


def test_destroy_continues_on_backend_errors(hop3_root, backend):
    """Destroy should clean up local state even if backend fails."""
    addon = S3Addon(addon_name="myapp", backend=backend)
    addon.create()

    # Simulate a backend that fails on delete_bucket
    backend.fail_next = "delete_bucket"
    addon.destroy()  # Should not raise

    # Local credentials file should still be cleaned up
    assert not (hop3_root / "addons" / "s3" / "myapp.json").exists()


def test_info_includes_backend_and_bucket(hop3_root, backend):
    addon = S3Addon(addon_name="myapp", backend=backend)
    addon.create()

    info = addon.info()
    assert info["addon_name"] == "myapp"
    assert info["type"] == "s3"
    assert info["backend"] == "stub"
    assert info["bucket"] == "hop3-myapp"
    assert info["has_credentials"] is True
    assert info["bucket_info"]["size"] == "0"


def test_backup_writes_manifest(hop3_root, backend):
    addon = S3Addon(addon_name="myapp", backend=backend)
    addon.create()

    backup_path = addon.backup()
    assert backup_path.exists()
    assert backup_path.name.startswith("myapp_")
    assert backup_path.suffix == ".json"

    # The backup should omit the secret key
    import json  # ruff:ignore[import-outside-top-level]

    data = json.loads(backup_path.read_text())
    assert data["addon_name"] == "myapp"
    assert data["bucket"] == "hop3-myapp"
    assert data["backend"] == "stub"
    assert data["credentials"]["access_key"] == "stub-hop3-myapp"
    # Secret key must NOT be in the backup manifest
    assert "secret_key" not in data["credentials"]
