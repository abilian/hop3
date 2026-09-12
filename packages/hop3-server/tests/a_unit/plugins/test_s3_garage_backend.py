# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
The Garage backend for the S3 addon.

Garage replaced MinIO because MinIO withdrew its public server binaries —
`dl.min.io` answers 410 and its GitHub releases carry no assets — so
`--with s3` could not be installed at all.

These drive the backend against a stub transport. The request shapes and
status codes they assert were taken from a real Garage v1.1.0, not from the
documentation: a duplicate bucket alias really does answer 409, deleting a
key twice really does answer 204 then 404, and a non-empty bucket really is
refused. The live-server counterpart is in tests/b_integration.
"""

from __future__ import annotations

import json

import httpx
import pytest

from hop3.plugins.s3.backend import BackendError, get_default_backend
from hop3.plugins.s3.garage import GarageBackend

BUCKET_ID = "e88f8a7ae0821fc364e0f82e21af4a5de85636252139b35f7d46eaab12023518"
ACCESS_KEY = "GK2fbf668921d1b98308c75a16"
SECRET_KEY = "b4fae947107910eb4ba8e0b0ab9cd9619433dbb693910a8915d702817c2bea56"


class FakeGarage:
    """A stand-in admin API that records what it was asked."""

    def __init__(self, routes: dict[tuple[str, str], tuple[int, object]]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, str, dict, object]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, path, dict(request.url.params), body))
        status, payload = self.routes.get((request.method, path), (404, None))
        if payload is None:
            return httpx.Response(status)
        return httpx.Response(status, json=payload)


def backend_with(monkeypatch, routes) -> tuple[GarageBackend, FakeGarage]:
    fake = FakeGarage(routes)
    transport = httpx.MockTransport(fake.handler)

    def request(method, url, **kwargs):
        with httpx.Client(transport=transport) as client:
            return client.request(method, url, **kwargs)

    monkeypatch.setattr(httpx, "request", request)
    return GarageBackend(admin_token="t"), fake


BUCKET = {"id": BUCKET_ID, "globalAliases": ["app-data"], "keys": [], "objects": 0}


class TestBucketsAreIdempotent:
    def test_creating_a_new_bucket_posts_the_alias(self, monkeypatch) -> None:
        backend, fake = backend_with(
            monkeypatch,
            {("GET", "/v1/bucket"): (404, None), ("POST", "/v1/bucket"): (200, BUCKET)},
        )
        backend.create_bucket("app-data")
        posts = [c for c in fake.calls if c[0] == "POST"]
        assert posts[0][3] == {"globalAlias": "app-data"}

    def test_an_existing_bucket_is_not_recreated(self, monkeypatch) -> None:
        """Garage answers 409 on a duplicate alias; the contract says idempotent."""
        backend, fake = backend_with(
            monkeypatch, {("GET", "/v1/bucket"): (200, BUCKET)}
        )
        backend.create_bucket("app-data")
        assert not [c for c in fake.calls if c[0] == "POST"]

    def test_deleting_an_absent_bucket_does_nothing(self, monkeypatch) -> None:
        backend, fake = backend_with(monkeypatch, {("GET", "/v1/bucket"): (404, None)})
        backend.delete_bucket("gone")
        assert not [c for c in fake.calls if c[0] == "DELETE"]


class TestKeysAreScopedToOneBucket:
    def test_a_new_key_is_granted_read_write_but_never_owner(self, monkeypatch) -> None:
        """An owner key could re-grant itself access to a neighbour's bucket."""
        backend, fake = backend_with(
            monkeypatch,
            {
                ("GET", "/v1/bucket"): (200, BUCKET),
                ("POST", "/v1/key"): (
                    200,
                    {"accessKeyId": ACCESS_KEY, "secretAccessKey": SECRET_KEY},
                ),
                ("POST", "/v1/bucket/allow"): (200, BUCKET),
            },
        )
        creds = backend.create_access_key("app-data")
        assert creds.access_key == ACCESS_KEY
        assert creds.secret_key == SECRET_KEY
        assert creds.region == "garage"
        allow = next(c for c in fake.calls if c[1] == "/v1/bucket/allow")
        assert allow[3]["permissions"] == {
            "read": True,
            "write": True,
            "owner": False,
        }
        assert allow[3]["bucketId"] == BUCKET_ID

    def test_a_key_for_a_missing_bucket_is_refused(self, monkeypatch) -> None:
        backend, _ = backend_with(monkeypatch, {("GET", "/v1/bucket"): (404, None)})
        with pytest.raises(BackendError, match="does not exist"):
            backend.create_access_key("nope")

    def test_deleting_a_key_twice_is_not_an_error(self, monkeypatch) -> None:
        """Garage answers 204 then 404; 'already gone' is the asked-for state."""
        backend, _ = backend_with(monkeypatch, {("DELETE", "/v1/key"): (404, None)})
        backend.delete_access_key(ACCESS_KEY)


class TestFailuresAreNamed:
    def test_an_unreachable_daemon_says_so(self, monkeypatch) -> None:
        refused = httpx.ConnectError("connection refused")

        def boom(*_a, **_k):
            raise refused

        monkeypatch.setattr(httpx, "request", boom)
        with pytest.raises(BackendError, match="unreachable"):
            GarageBackend(admin_token="t").list_buckets()

    def test_an_error_status_carries_the_body(self, monkeypatch) -> None:
        backend, _ = backend_with(
            monkeypatch, {("GET", "/v1/bucket"): (500, {"message": "boom"})}
        )
        with pytest.raises(BackendError, match="500"):
            backend.list_buckets()

    def test_a_response_of_the_wrong_shape_names_the_field(self, monkeypatch) -> None:
        """A v2 API move should say which field went missing."""
        backend, _ = backend_with(
            monkeypatch,
            {
                ("GET", "/v1/bucket"): (200, BUCKET),
                ("POST", "/v1/key"): (200, {"accessKeyId": ACCESS_KEY}),
            },
        )
        with pytest.raises(BackendError, match="secretAccessKey"):
            backend.create_access_key("app-data")

    def test_a_missing_token_names_the_file_and_the_install_flag(
        self, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.delenv("HOP3_GARAGE_ADMIN_TOKEN", raising=False)
        monkeypatch.setattr(
            "hop3.plugins.s3.garage.GARAGE_ADMIN_TOKEN_FILE",
            str(tmp_path / "absent"),
        )
        with pytest.raises(BackendError, match="--with s3"):
            GarageBackend().list_buckets()


class TestBucketInfo:
    def test_it_reports_objects_size_and_keys(self, monkeypatch) -> None:
        backend, _ = backend_with(
            monkeypatch,
            {
                ("GET", "/v1/bucket"): (
                    200,
                    {
                        "id": BUCKET_ID,
                        "globalAliases": ["app-data"],
                        "objects": 5,
                        "bytes": 500,
                        "keys": [{"accessKeyId": ACCESS_KEY}],
                    },
                )
            },
        )
        assert backend.bucket_info("app-data") == {
            "name": "app-data",
            "objects": "5",
            "size": "500",
            "keys": "1",
        }

    def test_listing_returns_global_aliases_sorted(self, monkeypatch) -> None:
        backend, _ = backend_with(
            monkeypatch,
            {
                ("GET", "/v1/bucket"): (
                    200,
                    [
                        {"id": "1", "globalAliases": ["zulu"]},
                        {"id": "2", "globalAliases": ["alpha", "bravo"]},
                        {"id": "3", "globalAliases": []},
                    ],
                )
            },
        )
        assert backend.list_buckets() == ["alpha", "bravo", "zulu"]


class TestTheDefaultBackend:
    def test_garage_is_what_a_server_gets(self, monkeypatch) -> None:
        monkeypatch.delenv("HOP3_S3_BACKEND", raising=False)
        assert get_default_backend().name == "garage"

    def test_minio_is_still_selectable_for_a_byo_server(self, monkeypatch) -> None:
        monkeypatch.setenv("HOP3_S3_BACKEND", "minio")
        assert get_default_backend().name == "minio"

    def test_an_unknown_backend_lists_the_known_ones(self, monkeypatch) -> None:
        monkeypatch.setenv("HOP3_S3_BACKEND", "ceph")
        with pytest.raises(ValueError, match="garage"):
            get_default_backend()
