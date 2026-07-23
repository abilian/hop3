# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Catalog sync: fetch, verify, and atomically publish the catalog (ADR 049).

Pipeline (each step fails loud — no silent fallback, CLAUDE.md):

1. ``fetch_to`` — HTTPS GET with a hard byte ceiling. TLS is always verified; an
   ``https→http`` redirect aborts; the CLI ``verify_ssl`` setting is never consulted
   here (catalog content becomes executed code).
2. ``verify_minisign`` (in ``verify.py``) on the downloaded tarball bytes, against the
   pinned public key — *before* the archive is ever opened.
3. ``extract_verified_tarball`` — into a private staging dir, rejecting symlinks,
   hardlinks, devices, absolute/``..`` paths, and bounding member count + total
   uncompressed size.
4. ``verify_tree_against_index`` — the staging tree must be exactly the signed
   ``index.json`` file set (F1).
5. anti-rollback — refuse a ``serial`` ≤ the persisted high-water-mark (F4).
6. ``_publish`` — rename staging → ``catalog-<serial>/`` and atomically flip the
   ``CATALOG_ROOT`` symlink (F2); persist the new serial; GC old versions.

The in-process ``CatalogService`` reload after a successful sync is the caller's job
(see the service wiring) — this module only owns the on-disk catalog.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import shutil
import ssl
import stat
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from .verify import verify_minisign, verify_tree_against_index

_SPECIAL_MODE_BITS = stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX

# Defensive ceilings. The catalog is curated and small; these bound a malicious or
# buggy artifact. ponytail: fixed limits, lift them if a real catalog approaches.
MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024  # 64 MiB compressed
MAX_UNCOMPRESSED_BYTES = 256 * 1024 * 1024  # 256 MiB extracted
MAX_MEMBERS = 10_000
FETCH_TIMEOUT = 30  # seconds

_INDEX_FILENAME = "index.json"
_SERIAL_FILENAME = "serial"


class CatalogSyncError(Exception):
    """Raised when fetching/extracting/publishing the catalog fails."""


class _HTTPSOnlyRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse to follow any redirect whose target is not HTTPS."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.lower().startswith("https://"):
            err = f"Catalog fetch refused a non-HTTPS redirect to {newurl!r}"
            raise urllib.error.HTTPError(newurl, code, err, headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@contextlib.contextmanager
def _exclusive_lock(state_root: Path):
    """
    Hold an exclusive, non-blocking lock for the publish critical section.

    Serializes concurrent ``hop3 catalog refresh`` runs so two of them cannot both
    pass the anti-rollback gate or race the symlink swap / GC.
    """
    state_root.mkdir(parents=True, exist_ok=True)
    fd = os.open(state_root / ".sync.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            msg = "Another catalog sync is already in progress"
            raise CatalogSyncError(msg) from e
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def fetch_to(url: str, dest: Path, *, max_bytes: int = MAX_DOWNLOAD_BYTES) -> None:
    """
    Download ``url`` to ``dest`` over verified HTTPS, capped at ``max_bytes``.

    TLS certificate verification is mandatory and not configurable here.
    """
    if not url.lower().startswith("https://"):
        msg = f"Catalog source URL must be https: {url!r}"
        raise CatalogSyncError(msg)

    context = ssl.create_default_context()  # verifies certs and hostname
    # Reject any non-HTTPS redirect *at redirect time* (before bytes move), so a
    # downgrade or SSRF hop can't transit cleartext / reach an internal host.
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=context),
        _HTTPSOnlyRedirectHandler(),
    )
    request = urllib.request.Request(
        url, method="GET", headers={"User-Agent": "hop3-catalog"}
    )
    try:
        with opener.open(request, timeout=FETCH_TIMEOUT) as response:
            final_url = response.geturl()
            if not final_url.lower().startswith("https://"):
                msg = f"Catalog fetch redirected off HTTPS to {final_url!r}"
                raise CatalogSyncError(msg)
            total = 0
            with dest.open("wb") as out:
                while chunk := response.read(1 << 16):
                    total += len(chunk)
                    if total > max_bytes:
                        msg = f"Catalog download exceeds the {max_bytes}-byte limit"
                        raise CatalogSyncError(msg)
                    out.write(chunk)
    except urllib.error.URLError as e:
        msg = f"Catalog fetch failed for {url!r}: {e}"
        raise CatalogSyncError(msg) from e


def extract_verified_tarball(
    tarball_path: Path,
    dest_dir: Path,
    *,
    max_uncompressed: int = MAX_UNCOMPRESSED_BYTES,
    max_members: int = MAX_MEMBERS,
) -> None:
    """
    Extract a ``.tar.gz`` into ``dest_dir``, rejecting anything unsafe.

    Streams member-by-member so caps abort early. Rejects symlinks, hardlinks,
    devices, absolute paths, and ``..`` traversal; bounds member count and total
    uncompressed size.
    """
    dest_real = dest_dir.resolve()
    total = 0
    count = 0
    try:
        with tarfile.open(tarball_path, "r:gz") as tar:
            for member in tar:
                count += 1
                if count > max_members:
                    msg = f"Catalog archive exceeds {max_members} members"
                    raise CatalogSyncError(msg)

                _reject_unsafe_member(member, dest_real)

                total += max(member.size, 0)
                if total > max_uncompressed:
                    msg = (
                        f"Catalog archive exceeds the {max_uncompressed}-byte "
                        "uncompressed limit"
                    )
                    raise CatalogSyncError(msg)

                # Strip setuid/setgid/sticky bits regardless of interpreter — the
                # "data" filter does this on 3.12+, but the fallback path (older
                # 3.11 without the filter kwarg) would not.
                member.mode &= ~_SPECIAL_MODE_BITS

                # member is validated above; the stdlib "data" filter is an extra
                # guard on Pythons that support it (3.12+), no-op fallback otherwise.
                try:
                    tar.extract(member, dest_dir, filter="data")
                except TypeError:
                    tar.extract(member, dest_dir)
    except tarfile.TarError as e:
        msg = f"Catalog archive is not a valid tar.gz: {e}"
        raise CatalogSyncError(msg) from e


def install_catalog_tarball(
    tarball_path: Path,
    signature_text: str,
    public_key: str,
    catalog_root: Path,
    state_root: Path,
    *,
    max_uncompressed: int = MAX_UNCOMPRESSED_BYTES,
    max_members: int = MAX_MEMBERS,
) -> int:
    """
    Verify, anti-rollback-check, and atomically publish a catalog tarball.

    Returns the published ``serial``. Raises ``CatalogSyncError`` /
    ``CatalogVerificationError`` on any failure, leaving the previously published
    catalog untouched.
    """
    tarball_bytes = tarball_path.read_bytes()
    verify_minisign(tarball_bytes, signature_text, public_key)

    parent = catalog_root.parent
    parent.mkdir(parents=True, exist_ok=True)
    # Staging lives next to CATALOG_ROOT (same filesystem → atomic rename) and is
    # never under a web-served path. 0700 so a co-tenant can't read/tamper.
    staging = Path(tempfile.mkdtemp(prefix=".catalog-staging-", dir=parent))
    published = False  # set once _publish has consumed staging (renamed or discarded)
    try:
        extract_verified_tarball(
            tarball_path,
            staging,
            max_uncompressed=max_uncompressed,
            max_members=max_members,
        )
        index = _load_index(staging)
        verify_tree_against_index(staging, index)
        serial = _index_serial(index)

        # The read-rollback-check → publish → record-serial → gc sequence must be
        # atomic across processes, or two refreshes could both pass anti-rollback or
        # race the swap/GC (SYNC-1/SYNC-2).
        with _exclusive_lock(state_root):
            hwm = read_high_water_mark(state_root)
            if serial <= hwm:
                msg = (
                    f"Catalog refused: serial {serial} is not newer than the "
                    f"installed serial {hwm} (possible rollback)"
                )
                raise CatalogSyncError(msg)

            _publish(staging, catalog_root, serial)
            published = True
            write_high_water_mark(state_root, serial)
            _gc_old_versions(parent, catalog_root=catalog_root, keep_serial=serial)
        return serial
    finally:
        if not published and staging.exists():
            _rmtree(staging)


def read_high_water_mark(state_root: Path) -> int:
    """
    Return the highest installed serial, or 0 if none recorded.

    A missing file means "not yet bootstrapped" and reads as 0 — the first
    verified catalog (serial ≥ 1) is then accepted. Resetting this by deleting the
    file re-opens rollback; the file is meant to live in write-protected,
    ideally root-owned state (ADR 049 F4/F8).
    """
    serial_file = state_root / _SERIAL_FILENAME
    if not serial_file.exists():
        return 0
    try:
        return int(serial_file.read_text().strip())
    except ValueError as e:
        msg = f"Corrupt catalog serial state at {serial_file}: {e}"
        raise CatalogSyncError(msg) from e


def write_high_water_mark(state_root: Path, serial: int) -> None:
    """Persist the new high-water-mark serial atomically."""
    state_root.mkdir(parents=True, exist_ok=True)
    serial_file = state_root / _SERIAL_FILENAME
    tmp = serial_file.with_suffix(".tmp")
    # fsync the data and the directory entry so the high-water-mark survives a
    # power loss (else a crash could leave catalog-N live but the serial at N-1).
    fd = os.open(tmp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    try:
        os.write(fd, f"{serial}\n".encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    tmp.replace(serial_file)
    dir_fd = os.open(state_root, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def _reject_unsafe_member(member: tarfile.TarInfo, dest_real: Path) -> None:
    if member.issym() or member.islnk():
        msg = f"Catalog archive contains a link, not allowed: {member.name!r}"
        raise CatalogSyncError(msg)
    if member.isdev() or member.ischr() or member.isblk() or member.isfifo():
        msg = f"Catalog archive contains a special file: {member.name!r}"
        raise CatalogSyncError(msg)
    if not (member.isfile() or member.isdir()):
        msg = f"Catalog archive contains an unsupported entry: {member.name!r}"
        raise CatalogSyncError(msg)

    name = member.name
    if name.startswith("/") or ".." in Path(name).parts:
        msg = f"Catalog archive path is unsafe: {name!r}"
        raise CatalogSyncError(msg)
    target = (dest_real / name).resolve()
    if target != dest_real and dest_real not in target.parents:
        msg = f"Catalog archive path escapes the destination: {name!r}"
        raise CatalogSyncError(msg)


def _load_index(catalog_dir: Path) -> dict:
    index_path = catalog_dir / _INDEX_FILENAME
    if not index_path.is_file():
        msg = f"Catalog is missing {_INDEX_FILENAME}"
        raise CatalogSyncError(msg)
    try:
        return json.loads(index_path.read_text())
    except (ValueError, OSError) as e:
        msg = f"Catalog {_INDEX_FILENAME} is unreadable/invalid: {e}"
        raise CatalogSyncError(msg) from e


def _index_serial(index: dict) -> int:
    serial = index.get("serial")
    if not isinstance(serial, int) or isinstance(serial, bool) or serial < 1:
        msg = f"Catalog index has an invalid serial: {serial!r}"
        raise CatalogSyncError(msg)
    return serial


def _publish(staging: Path, catalog_root: Path, serial: int) -> None:
    """
    Atomically publish ``staging`` as ``catalog-<serial>`` and flip the symlink.

    Idempotent and crash-safe: if ``catalog-<serial>`` is already the live target
    (e.g. a crash between the symlink flip and the serial write, or a same-serial
    re-publish), the staging tree is discarded and the live catalog is left intact —
    we never delete the directory the live symlink currently resolves to.
    """
    versioned = catalog_root.parent / f"{catalog_root.name}-{serial}"
    live = catalog_root.resolve() if catalog_root.is_symlink() else None

    if live is not None and versioned.is_dir() and live == versioned.resolve():
        _rmtree(staging)  # already published at this serial — nothing to do
        return

    if versioned.exists():
        _rmtree(versioned)  # stale leftover from an aborted run (not the live target)
    staging.rename(versioned)

    # Flip CATALOG_ROOT (a symlink) to the new versioned dir in one atomic replace.
    tmp_link = catalog_root.parent / f".{catalog_root.name}-link-{serial}"
    if tmp_link.exists() or tmp_link.is_symlink():
        tmp_link.unlink()
    tmp_link.symlink_to(versioned.name)  # relative target

    if catalog_root.is_symlink() or not catalog_root.exists():
        tmp_link.replace(catalog_root)
    elif catalog_root.is_dir():
        # First-ever publish where setup created a real (empty) dir: clear it.
        try:
            catalog_root.rmdir()
        except OSError as e:
            msg = (
                f"{catalog_root} is a non-empty directory where a managed symlink "
                f"is expected: {e}"
            )
            raise CatalogSyncError(msg) from e
        tmp_link.replace(catalog_root)
    else:
        tmp_link.unlink()
        msg = f"Unexpected non-directory at {catalog_root}"
        raise CatalogSyncError(msg)


def _gc_old_versions(parent: Path, *, catalog_root: Path, keep_serial: int) -> None:
    """
    Remove superseded ``<base_name>-<serial>`` dirs, keeping the current one.

    Only versioned dirs (numeric suffix) are touched — siblings such as
    ``catalog-state`` are left alone — and the directory the live symlink currently
    resolves to is never removed, even if it does not match ``keep_serial``.
    """
    base_name = catalog_root.name
    prefix = f"{base_name}-"
    keep = f"{prefix}{keep_serial}"
    live = catalog_root.resolve() if catalog_root.is_symlink() else None
    for child in parent.iterdir():
        if not child.is_dir() or child.is_symlink():
            continue
        if not child.name.startswith(prefix):
            continue
        if not child.name[len(prefix) :].isdigit():
            continue  # e.g. "catalog-state"
        if child.name == keep or child.resolve() == live:
            continue
        _rmtree(child)


def _rmtree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
