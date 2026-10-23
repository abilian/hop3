# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The few S3 operations Hop3 performs itself: list, get, put and delete.

Garage needs them to empty a bucket before dropping it, and the S3 addon to
back a bucket's objects up and put them back. Both talk to the server's own
object store, so a hand-signed SigV4 request over httpx is all it takes, and
no S3 SDK joins the server's dependencies. Requests are path-style: the store
is reached by IP on a loopback port, where a virtual-host style bucket name has
nowhere to live.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import hmac
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import IO, TYPE_CHECKING

import httpx

from .backend import BackendError

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = ["DEFAULT_CONTENT_TYPE", "S3Client"]

_TIMEOUT = 15.0

#: S3 caps a single ListObjectsV2 page at 1000 keys.
_LIST_PAGE = 1000

_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()

DEFAULT_CONTENT_TYPE = "application/octet-stream"


@dataclass(frozen=True)
class S3Client:
    """SigV4-signed requests to one S3 endpoint, with one key."""

    endpoint: str
    region: str
    access_key: str
    secret_key: str

    def list_keys(self, bucket: str) -> Iterator[str]:
        """Every object key in the bucket, following continuation tokens."""
        token: str | None = None
        while True:
            query = {"list-type": "2", "max-keys": str(_LIST_PAGE)}
            if token:
                query["continuation-token"] = token
            root = ET.fromstring(self._request("GET", f"/{bucket}", query).content)
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

    def download(self, bucket: str, key: str, dest: IO[bytes]) -> str:
        """Stream an object into ``dest``; return its content type."""
        path = f"/{bucket}/{key}"
        url, query, signed = self._signed("GET", path, None)
        with contextlib.ExitStack() as stack:
            try:
                response = stack.enter_context(
                    httpx.stream(
                        "GET", url, params=query, headers=signed, timeout=_TIMEOUT
                    )
                )
                if response.status_code >= httpx.codes.BAD_REQUEST:
                    response.read()
                    _raise_for_status("GET", path, response.status_code, response.text)
                for chunk in response.iter_bytes():
                    dest.write(chunk)
            except httpx.HTTPError as e:
                msg = f"S3 API at {self.endpoint} is unreachable: {e}"
                raise BackendError(msg) from e
            return response.headers.get("content-type", DEFAULT_CONTENT_TYPE)

    def upload(self, bucket: str, key: str, body: IO[bytes], content_type: str) -> None:
        """
        Store ``body`` (a seekable file) as an object.

        SigV4 signs the payload's hash, so the file is read twice: once to hash
        it, once to send it. Sent from a file, never held in memory.
        """
        digest = hashlib.sha256()
        size = 0
        body.seek(0)
        while chunk := body.read(1 << 20):
            digest.update(chunk)
            size += len(chunk)
        body.seek(0)
        self._request(
            "PUT",
            f"/{bucket}/{key}",
            content=body,
            payload_hash=digest.hexdigest(),
            headers={"Content-Type": content_type, "Content-Length": str(size)},
        )

    def delete(self, bucket: str, key: str) -> None:
        # The raw key: the request encodes once, for both the URL it sends and
        # the signature it computes over. Encoding here as well produced a
        # path saying `a%2Bb.txt` and a signature covering `a%252Bb.txt`, which
        # Garage rejected as "Invalid signature".
        self._request("DELETE", f"/{bucket}/{key}")

    # --- signing ------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        query: dict[str, str] | None = None,
        *,
        content: IO[bytes] | None = None,
        payload_hash: str = _EMPTY_SHA256,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        url, query, signed = self._signed(method, path, query, payload_hash, headers)
        try:
            response = httpx.request(
                method,
                url,
                params=query,
                headers=signed,
                content=content,
                timeout=_TIMEOUT,
            )
        except httpx.HTTPError as e:
            msg = f"S3 API at {self.endpoint} is unreachable: {e}"
            raise BackendError(msg) from e
        _raise_for_status(method, path, response.status_code, response.text)
        return response

    def _signed(
        self,
        method: str,
        path: str,
        query: dict[str, str] | None,
        payload_hash: str = _EMPTY_SHA256,
        headers: dict[str, str] | None = None,
    ) -> tuple[str, dict[str, str], dict[str, str]]:
        """The URL, query and headers of a SigV4-signed request."""
        query = query or {}
        # One encoding, used twice. SigV4 signs the encoded path, and the
        # server recomputes the signature from the path it received: if the
        # two spellings differ by so much as an escape, it is a 403.
        encoded_path = urllib.parse.quote(path, safe="/~")
        url = f"{self.endpoint.rstrip('/')}{encoded_path}"
        host = urllib.parse.urlsplit(self.endpoint).netloc
        now = dt.datetime.now(dt.UTC)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")

        canonical_query = "&".join(
            f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
            for k, v in sorted(query.items())
        )
        canonical_headers = (
            f"host:{host}\nx-amz-content-sha256:{payload_hash}\nx-amz-date:{amz_date}\n"
        )
        signed_headers = "host;x-amz-content-sha256;x-amz-date"
        # canonical_headers already ends in a newline; SigV4 wants a blank
        # line between the header block and the signed-header list, so the
        # explicit newline after it is load-bearing.
        canonical_request = (
            f"{method}\n{encoded_path}\n{canonical_query}\n"
            f"{canonical_headers}\n{signed_headers}\n{payload_hash}"
        )
        scope = f"{date_stamp}/{self.region}/s3/aws4_request"
        request_hash = hashlib.sha256(canonical_request.encode()).hexdigest()
        to_sign = f"AWS4-HMAC-SHA256\n{amz_date}\n{scope}\n{request_hash}"
        signing_key = _signing_key(self.secret_key, date_stamp, self.region)
        signature = hmac.new(signing_key, to_sign.encode(), hashlib.sha256).hexdigest()

        return (
            url,
            query,
            {
                **(headers or {}),
                "Host": host,
                "x-amz-content-sha256": payload_hash,
                "x-amz-date": amz_date,
                "Authorization": (
                    f"AWS4-HMAC-SHA256 Credential={self.access_key}/{scope}, "
                    f"SignedHeaders={signed_headers}, Signature={signature}"
                ),
            },
        )


def _raise_for_status(method: str, path: str, status: int, text: str) -> None:
    if status >= httpx.codes.BAD_REQUEST:
        msg = f"S3 {method} {path} returned {status}: {text.strip()[:300]}"
        raise BackendError(msg)


def _signing_key(secret_key: str, date_stamp: str, region: str) -> bytes:
    """The SigV4 derived signing key: date, region, service, terminator."""
    key = f"AWS4{secret_key}".encode()
    for part in (date_stamp, region, "s3", "aws4_request"):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    return key
