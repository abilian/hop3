# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
A build input is downloaded once, then served from cache.

uptime-kuma failed two consecutive golden runs on `curl: (22) ... error: 429`.
The recipe was fine; the address was rate-limited, because a catalog run pulls
twenty-odd tags from github.com within a few minutes and every deploy re-fetches
what the last one already had. `curl --retry` cannot help — a rate limit is not
a transient error, and asking again is the thing being punished.

So the fix is to stop asking: a shared, checksum-verified cache in front of the
downloads, keyed by content where the recipe pins a hash.
"""

from __future__ import annotations

import email.message
import hashlib
import urllib.error
from email.message import Message

import pytest

from hop3.lib import fetch as fetch_module
from hop3.lib.fetch import FetchError, cache_dir, fetch

PAYLOAD = b"upstream release tarball"
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()
URL = "https://example.invalid/app-1.0.tar.gz"


@pytest.fixture
def downloads(monkeypatch, tmp_path):
    """Serve PAYLOAD, counting how many times the network was actually used."""
    calls = []

    def fake_download(url: str, dest) -> None:
        calls.append(url)
        dest.write_bytes(PAYLOAD)

    monkeypatch.setattr(fetch_module, "_download", fake_download)
    return calls


def test_the_second_fetch_does_not_hit_the_network(downloads, tmp_path):
    """The whole point: N deploys of the same pinned version, one download."""
    first = fetch(URL, sha256=DIGEST, cache=tmp_path)
    second = fetch(URL, sha256=DIGEST, cache=tmp_path)

    assert first == second
    assert first.read_bytes() == PAYLOAD
    assert len(downloads) == 1


def test_a_pinned_hash_keys_the_cache_by_content(downloads, tmp_path):
    """Two recipes pinning the same artifact share one entry, whatever the URL."""
    fetch(URL, sha256=DIGEST, cache=tmp_path)
    fetch("https://mirror.invalid/other-name.tgz", sha256=DIGEST, cache=tmp_path)

    assert len(downloads) == 1


def test_an_unpinned_download_is_keyed_by_url(downloads, tmp_path):
    """Without a hash there is nothing else to key on, so URLs stay distinct."""
    fetch(URL, cache=tmp_path)
    fetch("https://example.invalid/other-1.0.tar.gz", cache=tmp_path)

    assert len(downloads) == 2


def test_wrong_bytes_never_reach_the_cache(downloads, tmp_path):
    """
    A mismatch must not be cached, or one bad download poisons every later one.

    It also must not leave the partial file behind for the next run to find.
    """
    wrong = hashlib.sha256(b"something else").hexdigest()

    with pytest.raises(FetchError, match="sha256 mismatch"):
        fetch(URL, sha256=wrong, cache=tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_the_cache_location_is_overridable(monkeypatch, tmp_path):
    """The Docker target points this at a volume that outlives the container."""
    monkeypatch.setenv("HOP3_DOWNLOAD_CACHE", str(tmp_path / "elsewhere"))

    assert cache_dir() == tmp_path / "elsewhere"


class _Response:
    """
    Minimal stand-in for what urlopen returns.

    Carries ``headers`` because every real response does, and the fetcher reads
    Content-Length from it to notice a body that arrived short. Pass
    ``declared`` to claim a length the body does not have.
    """

    def __init__(self, body: bytes, declared: int | None = None) -> None:
        self._body = body
        length = len(body) if declared is None else declared
        self.headers = email.message.Message()
        self.headers["Content-Length"] = str(length)

    def read(self, size: int = -1) -> bytes:
        chunk, self._body = self._body, b""
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *_) -> None:
        return None


def _http_error(code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError(URL, code, "rate limited", headers, None)


def test_a_rate_limit_is_retried_and_then_succeeds(monkeypatch, tmp_path):
    """429 is exactly the case this module exists for, so it must be retryable."""
    responses = [_http_error(429), _Response(PAYLOAD)]
    monkeypatch.setattr(fetch_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        fetch_module.urllib.request,
        "urlopen",
        lambda *_args, **_kw: _raise_or_return(responses.pop(0)),
    )

    assert fetch(URL, cache=tmp_path).read_bytes() == PAYLOAD
    assert responses == []


def test_a_missing_file_fails_immediately(monkeypatch, tmp_path):
    """Retrying a 404 only delays the error — the recipe asked for the wrong URL."""
    attempts = []

    def urlopen(*_args, **_kw):
        attempts.append(1)
        raise _http_error(404)

    monkeypatch.setattr(fetch_module.urllib.request, "urlopen", urlopen)

    with pytest.raises(FetchError, match="HTTP 404"):
        fetch(URL, cache=tmp_path)

    assert len(attempts) == 1


def test_the_server_decides_how_long_to_wait():
    """A Retry-After beats our backoff — it is the only informed number here."""
    assert fetch_module._retry_delay(0, _http_error(429, retry_after="30")) == 30.0


def test_backoff_grows_when_the_server_says_nothing():
    delays = [fetch_module._retry_delay(n, _http_error(429)) for n in range(4)]

    assert delays == [2.0, 4.0, 8.0, 16.0]


def _raise_or_return(item):
    if isinstance(item, Exception):
        raise item
    return item


def test_a_truncated_download_is_not_returned_as_success(tmp_path, monkeypatch):
    """
    A body that stops early is a failed download, not a short file.

    `copyfileobj` returns what it got and raises nothing, so the fetch reported
    success and the caller unpacked the fragment: mediawiki's tarball arrived
    68 MB short and died as `gzip: stdin: unexpected end of file`.
    """
    monkeypatch.setattr(fetch_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        fetch_module.urllib.request,
        "urlopen",
        lambda *_a, **_kw: _Response(PAYLOAD[:3], declared=len(PAYLOAD)),
    )

    with pytest.raises(fetch_module.FetchError, match="truncated"):
        fetch(URL, cache=tmp_path)


def test_a_truncated_download_never_reaches_the_cache(tmp_path, monkeypatch):
    """
    Otherwise the corruption outlives the network blip that caused it.

    Without a pinned sha256 there is nothing else to catch it, so a cached
    fragment would be served to every later build without touching the network.
    """
    monkeypatch.setattr(fetch_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        fetch_module.urllib.request,
        "urlopen",
        lambda *_a, **_kw: _Response(PAYLOAD[:3], declared=len(PAYLOAD)),
    )

    with pytest.raises(fetch_module.FetchError):
        fetch(URL, cache=tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_a_truncated_download_is_retried(tmp_path, monkeypatch):
    """A dropped connection is transient, so it gets the same retry as a 429."""
    responses = [
        _Response(PAYLOAD[:3], declared=len(PAYLOAD)),
        _Response(PAYLOAD),
    ]
    monkeypatch.setattr(fetch_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        fetch_module.urllib.request,
        "urlopen",
        lambda *_a, **_kw: responses.pop(0),
    )

    assert fetch(URL, cache=tmp_path).read_bytes() == PAYLOAD


def test_a_response_without_a_declared_length_is_accepted(tmp_path, monkeypatch):
    """
    Chunked and compressed-in-transit responses promise no length.

    There the size is genuinely unknown in advance, so the check has nothing to
    compare against and must not invent a failure.
    """
    response = _Response(PAYLOAD)
    del response.headers["Content-Length"]
    monkeypatch.setattr(
        fetch_module.urllib.request, "urlopen", lambda *_a, **_kw: response
    )

    assert fetch(URL, cache=tmp_path).read_bytes() == PAYLOAD


def test_refresh_discards_a_cached_copy(tmp_path, monkeypatch):
    """
    A cache hit is returned unread, so a bad entry needs a way out.

    The truncation check stops new corruption reaching the cache, but an entry
    written before it would be served to every later build forever, and the
    only remedy would be deleting a file inside the cache by hand on a server.
    """
    stale = tmp_path / fetch_module._cache_key(URL, None)
    stale.write_bytes(b"truncated")

    monkeypatch.setattr(
        fetch_module.urllib.request, "urlopen", lambda *_a, **_kw: _Response(PAYLOAD)
    )

    assert fetch(URL, cache=tmp_path, refresh=True).read_bytes() == PAYLOAD


def test_without_refresh_a_cached_copy_is_kept(tmp_path, monkeypatch):
    """The cache is the point; refresh is the exception, not the default."""
    cached = tmp_path / fetch_module._cache_key(URL, None)
    cached.write_bytes(b"already here")

    def _no_network(*_a, **_kw):
        msg = "a cache hit must not reach the network"
        raise AssertionError(msg)

    monkeypatch.setattr(fetch_module.urllib.request, "urlopen", _no_network)

    assert fetch(URL, cache=tmp_path).read_bytes() == b"already here"
