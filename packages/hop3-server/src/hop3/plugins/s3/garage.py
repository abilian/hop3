# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Garage backend for the S3 addon.

Garage (https://garagehq.deuxfleurs.fr/) replaced MinIO as the object store
Hop3 installs. MinIO withdrew its public server binaries — `dl.min.io` answers
410 and its GitHub releases carry no assets — so `--with s3` could no longer be
installed at all. Garage is a single static binary, S3-compatible, and aimed at
exactly the self-hosted case Hop3 serves.

Two protocols are involved and they are not interchangeable:

- The **admin API** (port 3903, bearer token) manages buckets and keys. It is
  plain JSON, so `httpx` is all it needs.
- The **S3 API** (port 3900, SigV4) is the only way to delete objects. Garage
  refuses to remove a bucket that still holds any — 409 from the admin API,
  "Bucket is not empty" from its CLI, and there is no force flag — so emptying
  a bucket before dropping it has to go through S3 itself. `mc rb --force` used
  to do this for MinIO; that tool is MinIO's, and keeping it as a dependency of
  the Garage path would mean the replacement still needed the thing it replaced.

Every endpoint and status code here was verified against a real Garage v1.1.0.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import os
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from .backend import BackendError, S3Credentials

if TYPE_CHECKING:
    from collections.abc import Iterator

    from hop3.lib.types import Json, JsonDict

__all__ = ["GARAGE_ADMIN_TOKEN_FILE", "GarageBackend"]

#: Where the installer writes the admin bearer token (0640 root:hop3).
GARAGE_ADMIN_TOKEN_FILE = "/etc/hop3/garage-admin-token"

#: Garage's own default region name. It is not AWS, but S3 clients insist on
#: one and SigV4 signs over it, so it has to match the server's `s3_region`.
GARAGE_REGION = "garage"

_TIMEOUT = 15.0

#: S3 caps a single ListObjectsV2 page at 1000 keys.
_LIST_PAGE = 1000

_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def _as_dict(value: Json, what: str) -> JsonDict:
    """A JSON object from the admin API, or a BackendError naming the shape."""
    if not isinstance(value, dict):
        msg = f"Garage admin API returned {type(value).__name__} for {what}, expected an object"
        raise BackendError(msg)
    return value


def _as_str(mapping: JsonDict, key: str, what: str) -> str:
    """
    A string field, checked rather than assumed.

    Garage's admin API is versioned and this code pins v1; reading a field
    that moved should say which field, not raise a TypeError three frames
    away when the value is spliced into a URL.
    """
    value = mapping.get(key)
    if not isinstance(value, str):
        msg = f"Garage admin API response for {what} has no string {key!r}"
        raise BackendError(msg)
    return value


def _read_admin_token() -> str:
    """
    The admin bearer token, or a BackendError naming what is missing.

    An empty token is not a usable default: Garage would answer 401 on every
    call and the operator would be left reading HTTP statuses instead of a
    sentence telling them the server was never installed with `--with s3`.
    """
    from_env = os.environ.get("HOP3_GARAGE_ADMIN_TOKEN")
    if from_env:
        return from_env
    token_file = Path(GARAGE_ADMIN_TOKEN_FILE)
    try:
        token = token_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        token = ""
    except OSError as e:
        msg = f"Garage admin token at {GARAGE_ADMIN_TOKEN_FILE} is unreadable: {e}"
        raise BackendError(msg) from e
    if not token:
        msg = (
            f"Garage admin token not found. Expected {GARAGE_ADMIN_TOKEN_FILE} "
            f"(or $HOP3_GARAGE_ADMIN_TOKEN). Was the server installed with "
            f"'--with s3'?"
        )
        raise BackendError(msg)
    return token


@dataclass
class GarageBackend:
    """S3 addon backend talking to a local Garage node."""

    name: str = "garage"
    endpoint: str = "http://127.0.0.1:3900"
    admin_endpoint: str = "http://127.0.0.1:3903"
    admin_token: str = field(default="")

    def _token(self) -> str:
        return self.admin_token or _read_admin_token()

    # --- admin API ---------------------------------------------------------

    def _admin(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | bool] | None = None,
        json_body: JsonDict | None = None,
        ok_missing: bool = False,
    ) -> Json:
        """
        Call the admin API and return the decoded body.

        ``ok_missing`` turns a 404 into ``None`` for the operations the addon
        contract requires to be idempotent: deleting a key twice answers 204
        then 404, and "already gone" is the state the caller asked for.
        """
        url = f"{self.admin_endpoint.rstrip('/')}{path}"
        headers = {"Authorization": f"Bearer {self._token()}"}
        try:
            response = httpx.request(
                method,
                url,
                params=params,
                json=json_body,
                headers=headers,
                timeout=_TIMEOUT,
            )
        except httpx.HTTPError as e:
            msg = f"Garage admin API at {self.admin_endpoint} is unreachable: {e}"
            raise BackendError(msg) from e

        if ok_missing and response.status_code == httpx.codes.NOT_FOUND:
            return None
        if response.status_code >= httpx.codes.BAD_REQUEST:
            msg = (
                f"Garage admin API {method} {path} returned "
                f"{response.status_code}: {response.text.strip()}"
            )
            raise BackendError(msg)
        if not response.content:
            return None
        return response.json()

    def _bucket_id(self, bucket: str) -> str | None:
        """The internal id Garage addresses a bucket by, or None if absent."""
        info = self._admin(
            "GET", "/v1/bucket", params={"globalAlias": bucket}, ok_missing=True
        )
        if info is None:
            return None
        return _as_str(_as_dict(info, "bucket"), "id", "bucket")

    def create_bucket(self, bucket: str) -> None:
        # Garage answers 409 when the alias exists; the addon contract says
        # idempotent, so an existing bucket is success, not a conflict.
        if self._bucket_id(bucket) is not None:
            return
        self._admin("POST", "/v1/bucket", json_body={"globalAlias": bucket})

    def delete_bucket(self, bucket: str) -> None:
        bucket_id = self._bucket_id(bucket)
        if bucket_id is None:
            return
        self._empty_bucket(bucket)
        self._admin("DELETE", "/v1/bucket", params={"id": bucket_id}, ok_missing=True)

    def create_access_key(self, bucket: str) -> S3Credentials:
        """
        Create a key that can reach this bucket and no other.

        Garage separates the two steps: a new key starts with access to
        nothing, and `bucket/allow` grants it read/write on one bucket. The
        key is never `owner`, so it cannot re-grant itself anything.
        """
        bucket_id = self._bucket_id(bucket)
        if bucket_id is None:
            msg = f"Cannot create a key for bucket {bucket!r}: it does not exist"
            raise BackendError(msg)

        key = _as_dict(
            self._admin("POST", "/v1/key", json_body={"name": f"hop3-{bucket}"}),
            "key creation",
        )
        access_key = _as_str(key, "accessKeyId", "key creation")
        secret_key = _as_str(key, "secretAccessKey", "key creation")

        self._admin(
            "POST",
            "/v1/bucket/allow",
            json_body={
                "bucketId": bucket_id,
                "accessKeyId": access_key,
                "permissions": {"read": True, "write": True, "owner": False},
            },
        )
        return S3Credentials(
            access_key=access_key,
            secret_key=secret_key,
            endpoint=self.endpoint,
            region=GARAGE_REGION,
        )

    def delete_access_key(self, access_key: str) -> None:
        self._admin("DELETE", "/v1/key", params={"id": access_key}, ok_missing=True)

    def list_buckets(self) -> list[str]:
        listing = self._admin("GET", "/v1/bucket", params={"list": True})
        if not isinstance(listing, list):
            return []
        names: list[str] = []
        for entry in listing:
            if not isinstance(entry, dict):
                continue
            aliases = entry.get("globalAliases")
            if not isinstance(aliases, list):
                continue
            names.extend(a for a in aliases if isinstance(a, str))
        return sorted(names)

    def bucket_info(self, bucket: str) -> dict[str, str]:
        info = self._admin(
            "GET", "/v1/bucket", params={"globalAlias": bucket}, ok_missing=True
        )
        if info is None:
            msg = f"Bucket {bucket!r} does not exist"
            raise BackendError(msg)
        data = _as_dict(info, "bucket info")
        keys = data.get("keys")
        return {
            "name": bucket,
            "objects": str(data.get("objects", 0)),
            "size": str(data.get("bytes", 0)),
            "keys": str(len(keys) if isinstance(keys, list) else 0),
        }

    # --- S3 API (only for emptying a bucket) -------------------------------

    def _empty_bucket(self, bucket: str) -> None:
        """
        Delete every object, because Garage will not drop a bucket holding any.

        Needs a key with owner rights on the bucket: the per-app keys are
        deliberately not owners. One is minted for the duration and removed
        afterwards, including when a delete fails — a leftover owner key on a
        bucket that still exists would be a standing grant nobody asked for.
        """
        bucket_id = self._bucket_id(bucket)
        if bucket_id is None:
            return
        key = _as_dict(
            self._admin("POST", "/v1/key", json_body={"name": f"hop3-purge-{bucket}"}),
            "purge key",
        )
        access_key = _as_str(key, "accessKeyId", "purge key")
        secret_key = _as_str(key, "secretAccessKey", "purge key")
        try:
            self._admin(
                "POST",
                "/v1/bucket/allow",
                json_body={
                    "bucketId": bucket_id,
                    "accessKeyId": access_key,
                    "permissions": {"read": True, "write": True, "owner": True},
                },
            )
            for object_key in self._list_objects(bucket, access_key, secret_key):
                self._delete_object(bucket, object_key, access_key, secret_key)
        finally:
            self.delete_access_key(access_key)

    def _list_objects(
        self, bucket: str, access_key: str, secret_key: str
    ) -> Iterator[str]:
        """Every object key in the bucket, following continuation tokens."""
        token: str | None = None
        while True:
            query = {"list-type": "2", "max-keys": str(_LIST_PAGE)}
            if token:
                query["continuation-token"] = token
            body = self._s3("GET", f"/{bucket}", query, access_key, secret_key).content
            root = ET.fromstring(body)
            namespace = (
                {"s3": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}
            )
            prefix = "s3:" if namespace else ""
            for contents in root.findall(f"{prefix}Contents", namespace):
                element = contents.find(f"{prefix}Key", namespace)
                if element is not None and element.text:
                    yield element.text
            truncated = root.find(f"{prefix}IsTruncated", namespace)
            if truncated is None or truncated.text != "true":
                return
            next_token = root.find(f"{prefix}NextContinuationToken", namespace)
            if next_token is None or not next_token.text:
                return
            token = next_token.text

    def _delete_object(
        self, bucket: str, key: str, access_key: str, secret_key: str
    ) -> None:
        path = f"/{bucket}/{urllib.parse.quote(key)}"
        self._s3("DELETE", path, {}, access_key, secret_key)

    def _s3(
        self,
        method: str,
        path: str,
        query: dict[str, str],
        access_key: str,
        secret_key: str,
    ) -> httpx.Response:
        """
        A SigV4-signed request to Garage's S3 API.

        Only two operations need this (list and delete), and both send no body,
        so the signature covers the empty-payload hash. Path-style addressing
        is used because Garage is reached by IP on a loopback port, where a
        virtual-host style bucket name has nowhere to live.
        """
        url = f"{self.endpoint.rstrip('/')}{path}"
        host = urllib.parse.urlsplit(self.endpoint).netloc
        now = dt.datetime.now(dt.UTC)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")

        canonical_query = "&".join(
            f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
            for k, v in sorted(query.items())
        )
        canonical_headers = (
            f"host:{host}\n"
            f"x-amz-content-sha256:{_EMPTY_SHA256}\n"
            f"x-amz-date:{amz_date}\n"
        )
        signed_headers = "host;x-amz-content-sha256;x-amz-date"
        canonical_request = "\n".join([
            method,
            urllib.parse.quote(path, safe="/~"),
            canonical_query,
            canonical_headers,
            signed_headers,
            _EMPTY_SHA256,
        ])
        scope = f"{date_stamp}/{GARAGE_REGION}/s3/aws4_request"
        to_sign = "\n".join([
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ])
        signing_key = _signing_key(secret_key, date_stamp)
        signature = hmac.new(signing_key, to_sign.encode(), hashlib.sha256).hexdigest()

        headers = {
            "Host": host,
            "x-amz-content-sha256": _EMPTY_SHA256,
            "x-amz-date": amz_date,
            "Authorization": (
                f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
                f"SignedHeaders={signed_headers}, Signature={signature}"
            ),
        }
        try:
            response = httpx.request(
                method, url, params=query, headers=headers, timeout=_TIMEOUT
            )
        except httpx.HTTPError as e:
            msg = f"Garage S3 API at {self.endpoint} is unreachable: {e}"
            raise BackendError(msg) from e
        if response.status_code >= httpx.codes.BAD_REQUEST:
            msg = (
                f"Garage S3 {method} {path} returned "
                f"{response.status_code}: {response.text.strip()[:300]}"
            )
            raise BackendError(msg)
        return response


def _signing_key(secret_key: str, date_stamp: str) -> bytes:
    """The SigV4 derived signing key: date, region, service, terminator."""
    key = f"AWS4{secret_key}".encode()
    for part in (date_stamp, GARAGE_REGION, "s3", "aws4_request"):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    return key
