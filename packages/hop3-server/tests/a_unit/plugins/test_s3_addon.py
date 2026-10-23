# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Tests for the S3Addon class.

Uses a stub backend to avoid needing a real Garage server, and an in-memory
S3 API behind httpx for the objects backup and restore move. The same
operations run against a real node in b_integration/test_s3_garage_integration.
"""

from __future__ import annotations

import tarfile
import urllib.parse
import xml.sax.saxutils
from dataclasses import dataclass, field

import httpx
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


class FakeS3:
    """An in-memory S3 API: list (one page), get, put and delete."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[bytes, str]] = {}
        self.fail_get = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        bucket, _, key = (
            urllib.parse.unquote(request.url.path).lstrip("/").partition("/")
        )
        if request.method == "GET" and not key:
            keys = sorted(k for b, k in self.objects if b == bucket)
            contents = "".join(
                f"<Contents><Key>{xml.sax.saxutils.escape(k)}</Key></Contents>"
                for k in keys
            )
            return httpx.Response(
                200,
                content=f"<ListBucketResult>{contents}"
                "<IsTruncated>false</IsTruncated></ListBucketResult>",
            )
        if request.method == "GET":
            if self.fail_get:
                return httpx.Response(500, text="disk on fire")
            body, content_type = self.objects[bucket, key]
            return httpx.Response(
                200, content=body, headers={"content-type": content_type}
            )
        if request.method == "PUT":
            self.objects[bucket, key] = (
                request.read(),
                request.headers["content-type"],
            )
            return httpx.Response(200)
        if request.method == "DELETE":
            self.objects.pop((bucket, key), None)
            return httpx.Response(204)
        return httpx.Response(405)

    def bucket(self, bucket: str) -> dict[str, tuple[bytes, str]]:
        return {k: v for (b, k), v in self.objects.items() if b == bucket}


@pytest.fixture
def s3(monkeypatch) -> FakeS3:
    fake = FakeS3()
    client = httpx.Client(transport=httpx.MockTransport(fake.handler))
    monkeypatch.setattr(httpx, "request", client.request)
    monkeypatch.setattr(httpx, "stream", client.stream)
    return fake


OBJECTS = {
    "index.html": (b"<h1>hi</h1>", "text/html"),
    "a b+c%.txt": (b"awkward", "text/plain"),
    "folder/": (b"", "application/x-directory"),
    "deep/" + "x" * 120: (b"long", "application/octet-stream"),
}


def test_a_restore_gives_back_exactly_the_backup(hop3_root, backend, s3):
    addon = S3Addon(addon_name="myapp", backend=backend)
    addon.create()
    for key, value in OBJECTS.items():
        s3.objects[addon.bucket_name, key] = value
    backup = addon.backup()

    s3.objects.pop((addon.bucket_name, "index.html"))
    s3.objects[addon.bucket_name, "added-later"] = (b"x", "text/plain")
    addon.restore(backup)

    assert s3.bucket(addon.bucket_name) == OBJECTS


def test_a_failed_backup_leaves_no_archive(hop3_root, backend, s3):
    addon = S3Addon(addon_name="myapp", backend=backend)
    addon.create()
    s3.objects[addon.bucket_name, "f"] = (b"x", "text/plain")
    s3.fail_get = True

    with pytest.raises(BackendError, match="disk on fire"):
        addon.backup()

    assert list((hop3_root / "backups" / "s3").iterdir()) == []


def test_a_manifest_from_before_0_8_is_refused(hop3_root, backend, s3):
    addon = S3Addon(addon_name="myapp", backend=backend)
    addon.create()
    s3.objects[addon.bucket_name, "keep"] = (b"live", "text/plain")
    legacy = hop3_root / "backups" / "s3" / "old.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text('{"addon_name": "myapp"}')

    with pytest.raises(ValueError, match="holds none of its objects"):
        addon.restore(legacy)

    assert s3.bucket(addon.bucket_name) == {"keep": (b"live", "text/plain")}


def test_an_archive_holding_more_than_objects_is_refused(hop3_root, backend, s3):
    addon = S3Addon(addon_name="myapp", backend=backend)
    addon.create()
    archive = hop3_root / "backups" / "s3" / "odd.tar"
    archive.parent.mkdir(parents=True)
    with tarfile.open(archive, "w") as tar:
        link = tarfile.TarInfo("link")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        tar.addfile(link)

    with pytest.raises(ValueError, match="not an S3 object backup"):
        addon.restore(archive)


def test_a_restore_reads_only_from_the_backup_tree(hop3_root, backend, tmp_path):
    addon = S3Addon(addon_name="myapp", backend=backend)
    addon.create()
    outside = tmp_path.parent / "elsewhere.tar"

    with pytest.raises(ValueError, match="outside the backup directory"):
        addon.restore(outside)
