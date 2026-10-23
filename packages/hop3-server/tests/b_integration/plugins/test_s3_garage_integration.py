# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
The Garage backend against a real Garage node.

The unit tests pin the request shapes against a stub. This one proves the
shapes are the ones Garage actually accepts — including the parts no stub can
check: that a key scoped to one bucket is refused everywhere else, and that a
bucket full of objects can still be deleted. Garage refuses to drop a
non-empty bucket (409 from the API, "Bucket is not empty" from its CLI, and no
force flag), so ``delete_bucket`` empties it over the S3 API first, with SigV4
signed by hand. A signature bug is invisible to a stub and fatal here.

Opt-in: point ``HOP3_TEST_GARAGE_ADMIN`` at a node's admin API. Nothing in CI
provisions one, and a skip whose reason is "no server" would be a hole
pretending to be coverage, so this stays explicit rather than auto-detected.

    docker run -d --name garage-dev -p 13900:3900 -p 13903:3903 \\
        -v /path/to/garage.toml:/etc/garage.toml:ro dxflrs/garage:v1.1.0
    docker exec garage-dev /garage layout assign -z dc1 -c 10G <node-id>
    docker exec garage-dev /garage layout apply --version 1

    HOP3_TEST_GARAGE_ADMIN=http://127.0.0.1:13903 \\
    HOP3_TEST_GARAGE_S3=http://127.0.0.1:13900 \\
    HOP3_TEST_GARAGE_TOKEN=devtoken uv run pytest <this file>
"""

from __future__ import annotations

import os
import uuid

import pytest

from hop3.config import HopConfig
from hop3.plugins.addons import generic_cli
from hop3.plugins.s3 import cli as s3_cli
from hop3.plugins.s3.backend import S3Credentials
from hop3.plugins.s3.garage import GarageBackend
from hop3.plugins.s3.s3 import S3Addon

ADMIN = os.environ.get("HOP3_TEST_GARAGE_ADMIN")
S3_ENDPOINT = os.environ.get("HOP3_TEST_GARAGE_S3", "http://127.0.0.1:3900")
TOKEN = os.environ.get("HOP3_TEST_GARAGE_TOKEN", "")

pytestmark = pytest.mark.skipif(
    not ADMIN,
    reason="set HOP3_TEST_GARAGE_ADMIN to run against a real Garage node",
)


@pytest.fixture
def backend() -> GarageBackend:
    return GarageBackend(
        endpoint=S3_ENDPOINT, admin_endpoint=ADMIN or "", admin_token=TOKEN
    )


@pytest.fixture
def bucket(backend: GarageBackend):
    """A bucket that is removed however the test ends."""
    name = f"hop3-it-{uuid.uuid4().hex[:10]}"
    backend.create_bucket(name)
    try:
        yield name
    finally:
        backend.delete_bucket(name)


def s3_client(creds):
    boto3 = pytest.importorskip("boto3", reason="boto3 drives the S3 side")
    import botocore.config  # ruff:ignore[import-outside-top-level]

    return boto3.client(
        "s3",
        endpoint_url=creds.endpoint,
        aws_access_key_id=creds.access_key,
        aws_secret_access_key=creds.secret_key,
        region_name=creds.region,
        config=botocore.config.Config(s3={"addressing_style": "path"}),
    )


class TestTheLifecycleTheAddonDependsOn:
    def test_create_is_idempotent(self, backend, bucket) -> None:
        backend.create_bucket(bucket)
        assert bucket in backend.list_buckets()

    def test_a_key_can_write_its_own_bucket(self, backend, bucket) -> None:
        creds = backend.create_access_key(bucket)
        client = s3_client(creds)
        client.put_object(Bucket=bucket, Key="hello.txt", Body=b"it works")
        body = client.get_object(Bucket=bucket, Key="hello.txt")["Body"].read()
        assert body == b"it works"

    def test_a_key_cannot_reach_another_bucket(self, backend, bucket) -> None:
        """The isolation the addon promises between apps."""
        other = f"{bucket}-neighbour"
        backend.create_bucket(other)
        try:
            creds = backend.create_access_key(bucket)
            client = s3_client(creds)
            with pytest.raises(Exception, match=r"NoSuchBucket|AccessDenied"):
                client.list_objects_v2(Bucket=other)
        finally:
            backend.delete_bucket(other)

    def test_bucket_info_counts_what_was_written(self, backend, bucket) -> None:
        creds = backend.create_access_key(bucket)
        client = s3_client(creds)
        for i in range(3):
            client.put_object(Bucket=bucket, Key=f"f{i}", Body=b"x" * 10)
        info = backend.bucket_info(bucket)
        assert info["objects"] == "3"
        assert info["size"] == "30"

    def test_a_bucket_holding_objects_is_still_deleted(self, backend) -> None:
        """
        Garage refuses a non-empty bucket, so this exercises the hand-rolled
        SigV4 list-and-delete. A destroy that left the data behind would be a
        teardown failure, not a cosmetic one.
        """
        name = f"hop3-it-{uuid.uuid4().hex[:10]}"
        backend.create_bucket(name)
        creds = backend.create_access_key(name)
        client = s3_client(creds)
        for i in range(5):
            client.put_object(Bucket=name, Key=f"dir/obj-{i}", Body=b"data")
        backend.delete_bucket(name)
        assert name not in backend.list_buckets()

    def test_keys_needing_url_encoding_are_deleted(self, backend) -> None:
        """
        Regression. `_delete_object` used to percent-encode the key, and
        `_s3` encoded the whole path again for the signature — so the request
        said `a%2Bb.txt` while the signature covered `a%252Bb.txt` and Garage
        answered "Invalid signature". An object whose key held a space or a
        `+` could not be deleted, and the bucket holding it could not be
        dropped, so destroying the app left its data behind.

        The earlier tests all used keys like `hello.txt` and `dir/obj-0`,
        which need no encoding, which is exactly why this survived them.
        """
        name = f"hop3-it-{uuid.uuid4().hex[:10]}"
        backend.create_bucket(name)
        creds = backend.create_access_key(name)
        client = s3_client(creds)
        awkward = [
            "with space.txt",
            "a+b.txt",
            "100% done.txt",
            "sub/dir/файл.txt",
            "quote'd.txt",
            "tilde~.txt",
        ]
        for key in awkward:
            client.put_object(Bucket=name, Key=key, Body=b"x")
        assert backend.bucket_info(name)["objects"] == str(len(awkward))

        backend.delete_bucket(name)
        assert name not in backend.list_buckets()

    def test_a_bucket_of_many_objects_is_emptied_across_pages(
        self, backend, monkeypatch
    ) -> None:
        """
        Listing pages, and the page is consumed while its objects are being
        deleted. Driven with a tiny page size rather than a thousand objects.
        """
        monkeypatch.setattr("hop3.plugins.s3.s3api._LIST_PAGE", 2)
        name = f"hop3-it-{uuid.uuid4().hex[:10]}"
        backend.create_bucket(name)
        creds = backend.create_access_key(name)
        client = s3_client(creds)
        for i in range(7):
            client.put_object(Bucket=name, Key=f"obj-{i:02d}", Body=b"x")
        backend.delete_bucket(name)
        assert name not in backend.list_buckets()

    def test_deletes_are_idempotent(self, backend) -> None:
        name = f"hop3-it-{uuid.uuid4().hex[:10]}"
        backend.create_bucket(name)
        creds = backend.create_access_key(name)
        backend.delete_bucket(name)
        backend.delete_bucket(name)
        backend.delete_access_key(creds.access_key)
        backend.delete_access_key(creds.access_key)


# --- the addon's backup and restore, against the same node ----------------


@pytest.fixture
def hop3_root(tmp_path, monkeypatch):
    monkeypatch.setenv("HOP3_ROOT", str(tmp_path))
    monkeypatch.setattr(generic_cli, "HOP3_ROOT", tmp_path)
    HopConfig.reset_instance()
    yield tmp_path
    HopConfig.reset_instance()


@pytest.fixture
def make_addon(backend, hop3_root):
    """S3 addons on the node, destroyed however the test ends."""
    made: list[S3Addon] = []

    def make() -> S3Addon:
        addon = S3Addon(addon_name=f"it-{uuid.uuid4().hex[:10]}", backend=backend)
        addon.create()
        made.append(addon)
        return addon

    yield make
    for addon in made:
        addon.destroy()


def app_client(addon: S3Addon):
    """The client the app itself would use, from its injected env."""
    env = addon.get_connection_details()
    return s3_client(
        S3Credentials(
            access_key=env["S3_ACCESS_KEY"],
            secret_key=env["S3_SECRET_KEY"],
            endpoint=env["S3_ENDPOINT"],
            region=env["S3_REGION"],
        )
    )


def bucket_contents(addon: S3Addon) -> dict[str, tuple[bytes, str]]:
    client = app_client(addon)
    listing = client.list_objects_v2(Bucket=addon.bucket_name).get("Contents", [])
    out = {}
    for entry in listing:
        obj = client.get_object(Bucket=addon.bucket_name, Key=entry["Key"])
        out[entry["Key"]] = (obj["Body"].read(), obj["ContentType"])
    return out


#: Keys that need encoding, a folder marker, a key past tar's 100-character
#: name field, and an object larger than one read chunk.
OBJECTS = {
    "index.html": (b"<h1>hello</h1>", "text/html"),
    "with space+plus%.txt": (b"awkward", "text/plain"),
    "sub/dir/файл.json": (b'{"a": 1}', "application/json"),
    "folder/": (b"", "application/x-directory"),
    "deep/" + "x" * 120 + ".bin": (b"long name", "application/octet-stream"),
    "big.bin": (bytes(range(256)) * 12_000, "application/octet-stream"),
}


def put_objects(addon: S3Addon, objects) -> None:
    client = app_client(addon)
    for key, (body, content_type) in objects.items():
        client.put_object(
            Bucket=addon.bucket_name, Key=key, Body=body, ContentType=content_type
        )


class TestTheAddonBacksUpAndRestoresObjects:
    """
    An S3 backup used to be a JSON manifest of the bucket's metadata, and its
    restore read it and discarded it: `restore`, `clone` and `import` all
    reported success and put back no object.
    """

    def test_a_restore_gives_back_exactly_the_backup(self, make_addon) -> None:
        addon = make_addon()
        put_objects(addon, OBJECTS)
        backup = addon.backup()

        client = app_client(addon)
        client.delete_object(Bucket=addon.bucket_name, Key="index.html")
        client.put_object(Bucket=addon.bucket_name, Key="big.bin", Body=b"changed")
        client.put_object(Bucket=addon.bucket_name, Key="added-later", Body=b"x")

        addon.restore(backup)

        assert bucket_contents(addon) == OBJECTS

    def test_a_clone_copies_the_objects(self, make_addon) -> None:
        source, target = make_addon(), make_addon()
        put_objects(source, OBJECTS)

        target.restore(source.backup())

        assert bucket_contents(target) == OBJECTS

    def test_import_loads_an_export_from_the_client(
        self, make_addon, monkeypatch
    ) -> None:
        source, target = make_addon(), make_addon()
        put_objects(source, OBJECTS)
        monkeypatch.setattr(generic_cli, "get_addon", lambda t, n: source)
        exported = next(
            item
            for item in s3_cli.AddonS3ExportCmd().call(source.addon_name)
            if item["t"] == "blob"
        )

        monkeypatch.setattr(generic_cli, "get_addon", lambda t, n: target)
        s3_cli.AddonS3ImportCmd().call(target.addon_name, import_data=exported["data"])

        assert bucket_contents(target) == OBJECTS

    def test_a_manifest_from_before_0_8_is_refused(self, make_addon, hop3_root) -> None:
        addon = make_addon()
        put_objects(addon, {"keep.txt": (b"live", "text/plain")})
        legacy = hop3_root / "backups" / "s3" / "old.json"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text('{"addon_name": "x", "bucket": "hop3-x"}')

        with pytest.raises(ValueError, match="holds none of its objects"):
            addon.restore(legacy)

        assert bucket_contents(addon) == {"keep.txt": (b"live", "text/plain")}
