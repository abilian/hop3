# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
``hop3-fetch`` — download a build input once, then serve it from cache.

Recipes fetch their upstream source in ``[build].before-build``, and until now
each one did that with a bare ``curl``. Every deploy of the same app, pinned to
the same version, re-downloaded the same bytes. That is wasteful on a single
server and self-defeating across a catalog run: twenty-odd recipes pull tags
from ``github.com`` within a few minutes, GitHub's codeload rate-limits the
address, and deploys start failing with ``HTTP 429`` — which is what took
uptime-kuma down twice in a row while the recipe itself was fine.

Retries do not help against a rate limit. Not asking twice does.

The cache is content-addressed when the recipe pins a checksum (``--sha256``),
so two recipes pinning the same artifact share one entry; otherwise it is keyed
by URL. A pinned hash is verified before the download is admitted to the cache,
so a cache hit is proof the bytes are the ones the recipe asked for.

Usage, as a drop-in for the ``curl`` calls it replaces::

    hop3-fetch "$URL" -o app.tar.gz --sha256 "$SHA256"
    hop3-fetch "$URL" | tar xz
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from hop3.config import CACHE_ROOT

__all__ = ["CACHE_ENV_VAR", "FetchError", "cache_dir", "fetch", "main"]

#: Overrides the cache location. The Docker test target points this at a named
#: volume, so the cache outlives the container it was filled in.
CACHE_ENV_VAR = "HOP3_DOWNLOAD_CACHE"

ATTEMPTS = 6
BACKOFF_BASE = 2.0
MAX_BACKOFF = 60.0
TIMEOUT = 120
CHUNK = 1 << 16
USER_AGENT = "hop3-fetch"

# 429 and 503 are the rate-limit cases this exists for; the rest are transient
# by definition. Every other 4xx means the recipe asked for the wrong thing —
# retrying a 404 just delays the error.
RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


class FetchError(Exception):
    """A build input could not be obtained. Never recovered from — the build stops."""


def cache_dir() -> Path:
    """The directory holding downloaded build inputs."""
    override = os.environ.get(CACHE_ENV_VAR)
    return Path(override) if override else CACHE_ROOT / "downloads"


def fetch(
    url: str,
    *,
    sha256: str | None = None,
    cache: Path | None = None,
    refresh: bool = False,
) -> Path:
    """
    Return the path to a cached copy of ``url``, downloading it if absent.

    ``refresh`` discards any cached copy first. Needed because a cache hit is
    returned unread: an entry written by a version that accepted a short body
    would otherwise be served to every later build forever, and the only remedy
    would be deleting a file inside the cache by hand on the server. A pinned
    fetch could never be poisoned that way — verification happens before the
    file reaches the cache, and the key is the hash itself — so this is for the
    unpinned entries, which are keyed by URL and have nothing to check against.

    Raises:
        FetchError: if the download fails, or if a pinned ``sha256`` does not
            match what arrived. A mismatch never reaches the cache.
    """
    root = cache if cache is not None else cache_dir()
    # ponytail: the cache grows without bound. Add an LRU sweep when a real
    # server shows disk pressure — a catalog's worth of tarballs is ~2 GB.
    root.mkdir(parents=True, exist_ok=True)

    cached = root / _cache_key(url, sha256)
    if refresh and cached.exists():
        _report(f"discarding cached copy of {url}")
        cached.unlink()
    if cached.exists():
        _report(f"cache hit for {url}")
        return cached

    handle, name = tempfile.mkstemp(dir=root, prefix=".partial-")
    os.close(handle)
    partial = Path(name)
    try:
        _download(url, partial)
        if sha256:
            got = _sha256(partial)
            if got != sha256:
                msg = f"{url}: sha256 mismatch — pinned {sha256}, downloaded {got}"
                raise FetchError(msg)
        os.replace(partial, cached)
    finally:
        partial.unlink(missing_ok=True)

    return cached


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``hop3-fetch`` console script."""
    parser = argparse.ArgumentParser(
        prog="hop3-fetch",
        description="Download a build input through Hop3's shared cache.",
    )
    parser.add_argument("url", help="URL to fetch")
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="write to this file (default: stdout, so the output can be piped)",
    )
    parser.add_argument(
        "--sha256",
        help="expected content hash; a mismatch fails the build",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="discard any cached copy and download again",
    )
    args = parser.parse_args(argv)

    try:
        cached = fetch(args.url, sha256=args.sha256, refresh=args.refresh)
    except (FetchError, OSError) as e:
        # OSError covers an unwritable cache directory. Reported, not worked
        # around: a build whose input cannot be stored should stop here rather
        # than half-succeed.
        _report(str(e))
        return 1

    if args.output == "-":
        with cached.open("rb") as f:
            shutil.copyfileobj(f, sys.stdout.buffer, CHUNK)
    else:
        shutil.copyfile(cached, args.output)
    return 0


def _cache_key(url: str, sha256: str | None) -> str:
    """
    Content-addressed when the recipe pins a hash, URL-addressed otherwise.

    A pin is the stronger key: two recipes vendoring the same artifact from
    different mirrors share one entry, and the name says what the bytes are.
    """
    if sha256:
        return f"sha256-{sha256}"
    return f"url-{hashlib.sha256(url.encode()).hexdigest()}"


def _download(url: str, dest: Path) -> None:
    """Fetch ``url`` into ``dest``, backing off on transient and rate-limit errors."""
    for attempt in range(ATTEMPTS):
        # A fresh Request per attempt. The opener records redirect history on
        # the Request object it is given, so a reused one accumulates hops
        # across retries and eventually reports "would lead to an infinite
        # loop" — a wrong diagnosis for a URL that redirects exactly once
        # (github.com -> codeload.github.com does, for every catalog tarball).
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with (
                urllib.request.urlopen(request, timeout=TIMEOUT) as response,
                dest.open("wb") as out,
            ):
                shutil.copyfileobj(response, out, CHUNK)
                expected = _declared_length(response)
            written = dest.stat().st_size
            if expected is not None and written != expected:
                # A connection dropped mid-body leaves a short file and no
                # exception: `copyfileobj` returns what it got. Accepting it
                # reports a download that did not happen, and — because a
                # recipe without a pinned `sha256` has nothing else to check —
                # stores the truncation in the cache, so every later build
                # gets the same corrupt bytes without touching the network.
                # mediawiki's tarball arrived 68 MB short and unpacked as
                # `gzip: stdin: unexpected end of file`.
                msg = f"truncated: got {written} of {expected} bytes"
                raise FetchError(msg)
            return
        except (urllib.error.URLError, TimeoutError, FetchError) as e:
            if isinstance(e, urllib.error.HTTPError) and e.code not in RETRYABLE_STATUS:
                msg = f"{url}: HTTP {e.code} {e.reason}"
                raise FetchError(msg) from e
            if attempt == ATTEMPTS - 1:
                msg = f"{url}: {e} (gave up after {ATTEMPTS} attempts)"
                raise FetchError(msg) from e
            delay = _retry_delay(attempt, e)
            _report(f"{url}: {e} — retrying in {delay:.0f}s")
            time.sleep(delay)


def _declared_length(response: object) -> int | None:
    """
    The body length the server promised, when it promised one.

    Absent for a chunked or compressed-in-transit response, where the only
    honest answer is that the size is not known in advance; those fall back to
    the pinned `sha256`, or to nothing.
    """
    header = response.headers.get("Content-Length")  # type: ignore[attr-defined]
    if header is None:
        return None
    try:
        return int(header)
    except ValueError:
        return None


def _retry_delay(attempt: int, error: Exception) -> float:
    """Exponential backoff, unless the server said how long to wait."""
    if isinstance(error, urllib.error.HTTPError):
        after = error.headers.get("Retry-After", "").strip()
        if after.isdigit():
            return min(float(after), MAX_BACKOFF)
    return min(BACKOFF_BASE * 2**attempt, MAX_BACKOFF)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _report(message: str) -> None:
    """Progress and failures go to stderr, so stdout stays pipeable."""
    print(f"hop3-fetch: {message}", file=sys.stderr)
