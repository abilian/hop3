# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for catalog sync: extract safety, anti-rollback, atomic publish (ADR 049).

A full signed catalog tarball is built offline with ``cryptography`` (no ``minisign``
CLI needed). The negative tests exercise the security-relevant branches.
"""

from __future__ import annotations

import base64
import fcntl
import hashlib
import io
import json
import os
import tarfile
from typing import TYPE_CHECKING

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hop3.server.catalog.sync import (
    CatalogSyncError,
    extract_verified_tarball,
    fetch_to,
    install_catalog_tarball,
    read_high_water_mark,
)
from hop3.server.catalog.verify import CatalogVerificationError, sha256_file

if TYPE_CHECKING:
    from pathlib import Path

KEY_ID = b"\xaa\xbb\xcc\xdd\xee\xff\x00\x11"


# --- minisign signing helpers (mirror the verifier's expected format) --------


def _pubkey_text(priv: Ed25519PrivateKey) -> str:
    pub = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    body = base64.b64encode(b"Ed" + KEY_ID + pub).decode()
    return f"untrusted comment: pub\n{body}\n"


def _sign(priv: Ed25519PrivateKey, message: bytes) -> str:
    payload = hashlib.blake2b(message, digest_size=64).digest()
    sig = priv.sign(payload)
    line1 = base64.b64encode(b"ED" + KEY_ID + sig).decode()
    tc = "file:catalog.tar.gz"
    line2 = base64.b64encode(priv.sign(sig + tc.encode())).decode()
    return f"untrusted comment: sig\n{line1}\ntrusted comment: {tc}\n{line2}\n"


# --- catalog tarball builder -------------------------------------------------


def _build_catalog(tmp_path: Path, serial: int, apps: dict[str, dict[str, bytes]]):
    """Build a catalog source tree + index.json, return its directory."""
    src = tmp_path / f"build-{serial}"
    index = {"format": 1, "serial": serial, "apps": []}
    for app_id, files in apps.items():
        for name, content in files.items():
            p = src / app_id / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content)
        index["apps"].append({
            "id": app_id,
            "files": [
                {"path": f"{app_id}/{n}", "sha256": sha256_file(src / app_id / n)}
                for n in files
            ],
        })
    (src / "index.json").write_text(json.dumps(index))
    return src


def _tar_gz(src_dir: Path, dest: Path) -> None:
    with tarfile.open(dest, "w:gz") as tar:
        for p in sorted(src_dir.rglob("*")):
            tar.add(str(p), arcname=p.relative_to(src_dir).as_posix(), recursive=False)


def _signed_catalog(tmp_path, priv, serial=1, apps=None):
    apps = apps or {
        "nextcloud": {"hop3.toml": b"id='nextcloud'\n", "readme.md": b"# n\n"}
    }
    src = _build_catalog(tmp_path, serial, apps)
    tarball = tmp_path / f"catalog-{serial}.tar.gz"
    _tar_gz(src, tarball)
    return tarball, _sign(priv, tarball.read_bytes())


def _roots(tmp_path):
    return tmp_path / "home" / "catalog", tmp_path / "home" / "catalog-state"


# --- install_catalog_tarball -------------------------------------------------


def test_install_happy_path(tmp_path):
    priv = Ed25519PrivateKey.generate()
    catalog_root, state_root = _roots(tmp_path)
    tarball, sig = _signed_catalog(tmp_path, priv, serial=3)

    result = install_catalog_tarball(
        tarball, sig, _pubkey_text(priv), catalog_root, state_root
    )

    assert result.serial == 3
    assert result.changed is True
    assert catalog_root.is_symlink()
    assert catalog_root.resolve().name == "catalog-3"
    assert (
        catalog_root / "nextcloud" / "hop3.toml"
    ).read_bytes() == b"id='nextcloud'\n"
    assert read_high_water_mark(state_root) == 3


def test_install_rejects_tampered_tarball(tmp_path):
    priv = Ed25519PrivateKey.generate()
    catalog_root, state_root = _roots(tmp_path)
    tarball, sig = _signed_catalog(tmp_path, priv)
    tarball.write_bytes(tarball.read_bytes() + b"tamper")  # invalidate the signature

    with pytest.raises(CatalogVerificationError):
        install_catalog_tarball(
            tarball, sig, _pubkey_text(priv), catalog_root, state_root
        )
    assert not catalog_root.exists()  # nothing published


def test_install_rejects_rollback(tmp_path):
    priv = Ed25519PrivateKey.generate()
    catalog_root, state_root = _roots(tmp_path)

    t2, s2 = _signed_catalog(tmp_path, priv, serial=2)
    install_catalog_tarball(t2, s2, _pubkey_text(priv), catalog_root, state_root)

    t1, s1 = _signed_catalog(tmp_path, priv, serial=1)
    with pytest.raises(CatalogSyncError, match="rollback"):
        install_catalog_tarball(t1, s1, _pubkey_text(priv), catalog_root, state_root)
    assert catalog_root.resolve().name == "catalog-2"  # unchanged


def test_install_rejects_extra_file_not_in_index(tmp_path):
    priv = Ed25519PrivateKey.generate()
    catalog_root, state_root = _roots(tmp_path)
    src = _build_catalog(tmp_path, 1, {"app": {"hop3.toml": b"x"}})
    (src / "app" / "injected.sh").write_bytes(b"evil")  # present, not in index
    tarball = tmp_path / "c.tar.gz"
    _tar_gz(src, tarball)
    sig = _sign(priv, tarball.read_bytes())

    with pytest.raises(
        CatalogVerificationError, match="not listed in the signed index"
    ):
        install_catalog_tarball(
            tarball, sig, _pubkey_text(priv), catalog_root, state_root
        )


def test_second_publish_flips_symlink_and_gcs(tmp_path):
    priv = Ed25519PrivateKey.generate()
    catalog_root, state_root = _roots(tmp_path)

    t1, s1 = _signed_catalog(tmp_path, priv, serial=1)
    install_catalog_tarball(t1, s1, _pubkey_text(priv), catalog_root, state_root)
    t2, s2 = _signed_catalog(tmp_path, priv, serial=2)
    install_catalog_tarball(t2, s2, _pubkey_text(priv), catalog_root, state_root)

    assert catalog_root.resolve().name == "catalog-2"
    assert not (catalog_root.parent / "catalog-1").exists()  # GC'd
    assert read_high_water_mark(state_root) == 2


def test_crash_recovery_republish_keeps_live_catalog(tmp_path):
    # Simulate a crash between the symlink flip and the serial write: the catalog is
    # live at serial 2 but the recorded HWM is still 1. Re-installing serial 2 must
    # self-heal (re-record HWM) and must NOT delete the live directory (SYNC-1).
    priv = Ed25519PrivateKey.generate()
    catalog_root, state_root = _roots(tmp_path)
    t2, s2 = _signed_catalog(tmp_path, priv, serial=2)
    install_catalog_tarball(t2, s2, _pubkey_text(priv), catalog_root, state_root)
    (state_root / "serial").write_text("1\n")  # roll the recorded HWM back

    result = install_catalog_tarball(
        t2, s2, _pubkey_text(priv), catalog_root, state_root
    )

    assert result.serial == 2
    assert result.changed is True
    assert catalog_root.resolve().name == "catalog-2"
    assert (catalog_root / "nextcloud" / "hop3.toml").exists()  # live dir intact
    assert read_high_water_mark(state_root) == 2


def test_concurrent_sync_is_locked_out(tmp_path):
    priv = Ed25519PrivateKey.generate()
    catalog_root, state_root = _roots(tmp_path)
    tarball, sig = _signed_catalog(tmp_path, priv, serial=1)

    # Hold the sync lock as another process would.
    state_root.mkdir(parents=True, exist_ok=True)
    fd = os.open(state_root / ".sync.lock", os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        with pytest.raises(CatalogSyncError, match="already in progress"):
            install_catalog_tarball(
                tarball, sig, _pubkey_text(priv), catalog_root, state_root
            )
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def test_extract_strips_setuid_bits(tmp_path):
    tarball = tmp_path / "setuid.tar.gz"
    with tarfile.open(tarball, "w:gz") as tar:
        ti = tarfile.TarInfo("app/tool")
        ti.size = 1
        ti.mode = 0o4755  # setuid
        tar.addfile(ti, io.BytesIO(b"x"))
    out = tmp_path / "out"
    extract_verified_tarball(tarball, out)
    mode = (out / "app" / "tool").stat().st_mode
    assert not mode & 0o4000  # setuid stripped


# --- extract_verified_tarball ------------------------------------------------


def _tar_with_member(dest: Path, name: str, *, symlink=False, size=None):
    with tarfile.open(dest, "w:gz") as tar:
        if symlink:
            ti = tarfile.TarInfo(name)
            ti.type = tarfile.SYMTYPE
            ti.linkname = "/etc/passwd"
            tar.addfile(ti)
        else:
            data = b"x" * (size or 1)
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            tar.addfile(ti, io.BytesIO(data))


def test_extract_rejects_traversal(tmp_path):
    tarball = tmp_path / "evil.tar.gz"
    _tar_with_member(tarball, "../escape")
    with pytest.raises(CatalogSyncError, match=r"unsafe|escapes"):
        extract_verified_tarball(tarball, tmp_path / "out")


def test_extract_rejects_symlink(tmp_path):
    tarball = tmp_path / "evil.tar.gz"
    _tar_with_member(tarball, "app/link", symlink=True)
    with pytest.raises(CatalogSyncError, match="link"):
        extract_verified_tarball(tarball, tmp_path / "out")


def test_extract_rejects_oversized(tmp_path):
    tarball = tmp_path / "big.tar.gz"
    _tar_with_member(tarball, "app/blob", size=1000)
    with pytest.raises(CatalogSyncError, match="uncompressed limit"):
        extract_verified_tarball(tarball, tmp_path / "out", max_uncompressed=100)


def test_extract_rejects_too_many_members(tmp_path):
    tarball = tmp_path / "many.tar.gz"
    with tarfile.open(tarball, "w:gz") as tar:
        for i in range(5):
            ti = tarfile.TarInfo(f"app/f{i}")
            ti.size = 1
            tar.addfile(ti, io.BytesIO(b"x"))
    with pytest.raises(CatalogSyncError, match="members"):
        extract_verified_tarball(tarball, tmp_path / "out", max_members=2)


# --- fetch + state -----------------------------------------------------------


def test_fetch_rejects_non_https(tmp_path):
    with pytest.raises(CatalogSyncError, match="must be https"):
        fetch_to("http://example.com/catalog.tar.gz", tmp_path / "out.tar.gz")


def test_read_high_water_mark_missing_is_zero(tmp_path):
    assert read_high_water_mark(tmp_path / "nope") == 0


def test_install_reports_an_unchanged_catalog_as_a_no_op(tmp_path):
    """
    Re-installing the SAME serial is "nothing new" — not an attack, not an error.

    It used to raise, so `hop3 catalog refresh` printed "ERROR: refresh failed"
    for the wholly routine case of nobody having re-published yet. An OLDER
    serial is still refused; that is the real rollback.
    """
    priv = Ed25519PrivateKey.generate()
    catalog_root, state_root = _roots(tmp_path)

    t, s = _signed_catalog(tmp_path, priv, serial=7)
    install_catalog_tarball(t, s, _pubkey_text(priv), catalog_root, state_root)

    t_again, s_again = _signed_catalog(tmp_path, priv, serial=7)
    again = install_catalog_tarball(
        t_again, s_again, _pubkey_text(priv), catalog_root, state_root
    )

    assert again.serial == 7
    assert again.changed is False  # nothing written, nothing raised
    assert catalog_root.resolve().name == "catalog-7"  # still published
