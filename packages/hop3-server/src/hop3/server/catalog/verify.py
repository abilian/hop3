# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Catalog verification primitives (ADR 049).

Pure, side-effect-light functions for the catalog trust chain:

- ``verify_minisign`` — verify a detached minisign (Ed25519) signature against a
  pinned public key. The Hop3 team signs the catalog tarball offline with the
  standard ``minisign`` tool; the node verifies with the public key compiled into
  the release. No new dependency: ``cryptography`` is already a direct dependency.
- ``verify_tree_against_index`` — enforce that the extracted catalog directory is
  *exactly* the file set named in the (tarball-signed) ``index.json``: every listed
  file present with a matching SHA-256, and no unlisted file on disk. This closes
  the gap where the signature pins the tarball bytes but the loader executes the
  directory (ADR 049 F1).

These functions never fall back: any verification problem raises
``CatalogVerificationError`` (ADR 049 / CLAUDE.md fail-loud).
"""

from __future__ import annotations

import base64
import hashlib
import os
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

if TYPE_CHECKING:
    from collections.abc import Mapping

# minisign on-the-wire sizes (bytes), after base64-decoding each line.
_PUBKEY_LEN = 42  # 2 (algo) + 8 (key id) + 32 (Ed25519 public key)
_SIG_LEN = 74  # 2 (algo) + 8 (key id) + 64 (Ed25519 signature)
_GLOBAL_SIG_LEN = 64  # Ed25519 signature over (signature || trusted comment)
_ALGO_LEGACY = b"Ed"  # signature is over the raw file content
_ALGO_PREHASHED = b"ED"  # signature is over BLAKE2b-512 of the content
_TRUSTED_COMMENT_PREFIX = "trusted comment: "

_INDEX_FILENAME = "index.json"


class CatalogVerificationError(Exception):
    """Raised when catalog authenticity or integrity verification fails."""


def verify_minisign(message: bytes, signature_file: str, public_key: str) -> None:
    """
    Verify a detached minisign signature over ``message``.

    Args:
        message: the exact bytes that were signed (e.g. the tarball content).
        signature_file: the text of the ``.minisig`` file.
        public_key: the text of the minisign public-key file (or just its
            base64 body).

    Raises:
        CatalogVerificationError: on any malformed input, key-id mismatch, or
            signature that does not verify. Never returns a boolean — absence of
            an exception is the only success signal.
    """
    algo, key_id, signature, trusted_comment, global_sig = _parse_signature(
        signature_file
    )
    pk_key_id, pubkey_bytes = _parse_public_key(public_key)

    if key_id != pk_key_id:
        msg = (
            "Catalog signature key id does not match the pinned public key "
            f"(sig={key_id.hex()}, key={pk_key_id.hex()})"
        )
        raise CatalogVerificationError(msg)

    if algo == _ALGO_PREHASHED:
        signed = hashlib.blake2b(message, digest_size=64).digest()
    elif algo == _ALGO_LEGACY:
        signed = message
    else:
        msg = f"Unsupported minisign algorithm: {algo!r}"
        raise CatalogVerificationError(msg)

    public = Ed25519PublicKey.from_public_bytes(pubkey_bytes)
    try:
        public.verify(signature, signed)
    except InvalidSignature:
        msg = "Catalog signature is invalid for the pinned public key"
        raise CatalogVerificationError(msg) from None

    # The global signature binds the trusted comment to the file signature.
    # We do not rely on the trusted comment, but verifying it keeps us in lockstep
    # with `minisign -V` (a signature it would reject must not pass here).
    try:
        public.verify(global_sig, signature + trusted_comment.encode("utf-8"))
    except InvalidSignature:
        msg = "Catalog signature trusted-comment binding is invalid"
        raise CatalogVerificationError(msg) from None


def verify_tree_against_index(catalog_dir: Path, index: Mapping) -> None:
    """
    Require ``catalog_dir`` to be exactly the file set named in ``index``.

    The signed ``index.json`` is authoritative for *what exists*, not only for
    each file's hash. Every file listed under ``index["apps"][*]["files"]`` must
    exist with a matching SHA-256, and no other file may be present on disk
    (``index.json`` itself excepted). Symlinks are rejected outright.

    Raises:
        CatalogVerificationError: on any missing file, hash mismatch, unlisted
            extra file, conflicting duplicate entry, symlink, or declared path
            that escapes ``catalog_dir``.
    """
    base = catalog_dir.resolve()

    apps = index.get("apps", [])
    if not isinstance(apps, list):
        msg = "Catalog index 'apps' must be a list"
        raise CatalogVerificationError(msg)

    expected: dict[str, str] = {}
    for app in apps:
        if not isinstance(app, dict):
            msg = "Catalog index app entries must be objects"
            raise CatalogVerificationError(msg)
        files = app.get("files", [])
        if not isinstance(files, list):
            msg = "Catalog index app 'files' must be a list"
            raise CatalogVerificationError(msg)
        for entry in files:
            rel, digest = _index_entry(entry)
            target = _resolve_within(base, rel)
            key = target.relative_to(base).as_posix()
            if key in expected and expected[key] != digest:
                msg = f"Catalog index lists conflicting hashes for {rel!r}"
                raise CatalogVerificationError(msg)
            expected[key] = digest

    # The set bijection below assumes distinct index names map to distinct files.
    # On a case-insensitive or Unicode-normalizing volume two names could collide to
    # one inode; reject that up front so the invariant holds on any filesystem.
    _reject_normalization_collisions(expected)

    actual = _scan_files(base)

    missing = sorted(set(expected) - actual)
    if missing:
        msg = f"Catalog index lists files missing on disk: {missing}"
        raise CatalogVerificationError(msg)

    extra = sorted(actual - set(expected))
    if extra:
        msg = f"Catalog has files not listed in the signed index: {extra}"
        raise CatalogVerificationError(msg)

    for rel, digest in expected.items():
        got = sha256_file(base / rel)
        if got != digest:
            msg = f"Catalog file {rel!r} hash mismatch (index={digest}, disk={got})"
            raise CatalogVerificationError(msg)


def sha256_file(path: Path) -> str:
    """Return the hex SHA-256 of a file, read in chunks."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _scan_files(base: Path) -> set[str]:
    """
    Return all regular files under ``base`` (posix-relative), minus index.json.

    Rejects symlinks anywhere in the tree — a verified catalog has none, and a
    symlink is an exfiltration/escape vector if later copied into an app.
    """
    found: set[str] = set()
    for root, dirs, files in os.walk(base):  # followlinks defaults to False
        root_path = Path(root)
        for name in (*dirs, *files):
            if (root_path / name).is_symlink():
                rel = (root_path / name).relative_to(base).as_posix()
                msg = f"Catalog contains a symlink, which is not allowed: {rel!r}"
                raise CatalogVerificationError(msg)
        for name in files:
            rel = (root_path / name).relative_to(base).as_posix()
            if rel == _INDEX_FILENAME:
                continue
            found.add(rel)
    return found


def _index_entry(entry: object) -> tuple[str, str]:
    """
    Validate one index file entry, returning (path, sha256).

    The index is signed (trusted), so this guards against a malformed-but-signed
    index and honors the "all failures are CatalogVerificationError" contract.
    """
    if not isinstance(entry, dict):
        msg = "Catalog index file entries must be objects"
        raise CatalogVerificationError(msg)
    rel = entry.get("path")
    digest = entry.get("sha256")
    if not isinstance(rel, str):
        msg = f"Catalog index file path must be a string: {rel!r}"
        raise CatalogVerificationError(msg)
    if not (
        isinstance(digest, str)
        and len(digest) == 64
        and all(c in "0123456789abcdef" for c in digest)
    ):
        msg = f"Catalog index sha256 must be 64 lowercase hex chars: {digest!r}"
        raise CatalogVerificationError(msg)
    return rel, digest


def _reject_normalization_collisions(expected: dict[str, str]) -> None:
    seen: dict[str, str] = {}
    for key in expected:
        norm = unicodedata.normalize("NFC", key).casefold()
        if norm in seen:
            msg = (
                "Catalog index names collide under case/Unicode normalization: "
                f"{seen[norm]!r} vs {key!r}"
            )
            raise CatalogVerificationError(msg)
        seen[norm] = key


def _resolve_within(base: Path, rel: str) -> Path:
    """Resolve ``rel`` under ``base``, rejecting absolute paths and traversal."""
    if rel != rel.strip() or not rel or rel.startswith("/"):
        msg = f"Invalid catalog path: {rel!r}"
        raise CatalogVerificationError(msg)
    target = (base / rel).resolve()
    if target != base and base not in target.parents:
        msg = f"Catalog path escapes the catalog directory: {rel!r}"
        raise CatalogVerificationError(msg)
    return target


def _parse_public_key(text: str) -> tuple[bytes, bytes]:
    """Return (key_id, ed25519_public_key) from a minisign public key file."""
    raw = _decode_last_b64_line(text, "public key")
    if len(raw) != _PUBKEY_LEN:
        msg = f"Malformed minisign public key (got {len(raw)} bytes)"
        raise CatalogVerificationError(msg)
    return raw[2:10], raw[10:42]


def _parse_signature(text: str) -> tuple[bytes, bytes, bytes, str, bytes]:
    """
    Return (algo, key_id, signature, trusted_comment, global_sig).

    Parses minisign's canonical fixed 4-line layout positionally and rejects
    anything else (extra/missing/injected lines), so we stay in lockstep with
    ``minisign -V`` rather than silently accepting a file it would reject.
    """
    lines = [ln.rstrip("\r") for ln in text.strip().splitlines()]
    if len(lines) != 4:
        msg = f"Malformed minisign signature file (expected 4 lines, got {len(lines)})"
        raise CatalogVerificationError(msg)
    untrusted_line, sig_b64, trusted_line, global_b64 = lines

    if not untrusted_line.startswith("untrusted comment:"):
        msg = "Malformed minisign signature: missing untrusted comment"
        raise CatalogVerificationError(msg)

    sig_raw = _b64decode(sig_b64, "signature")
    if len(sig_raw) != _SIG_LEN:
        msg = f"Malformed minisign signature (got {len(sig_raw)} bytes)"
        raise CatalogVerificationError(msg)
    algo, key_id, signature = sig_raw[0:2], sig_raw[2:10], sig_raw[10:74]

    if not trusted_line.startswith(_TRUSTED_COMMENT_PREFIX):
        msg = "Missing minisign trusted comment"
        raise CatalogVerificationError(msg)
    trusted_comment = trusted_line[len(_TRUSTED_COMMENT_PREFIX) :]

    global_sig = _b64decode(global_b64, "trusted-comment signature")
    if len(global_sig) != _GLOBAL_SIG_LEN:
        msg = "Malformed minisign global signature"
        raise CatalogVerificationError(msg)

    return algo, key_id, signature, trusted_comment, global_sig


def _decode_last_b64_line(text: str, what: str) -> bytes:
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    body = [
        ln
        for ln in lines
        if not ln.startswith(("untrusted comment:", "trusted comment:"))
    ]
    if not body:
        msg = f"Empty minisign {what}"
        raise CatalogVerificationError(msg)
    return _b64decode(body[-1], what)


def _b64decode(line: str, what: str) -> bytes:
    try:
        return base64.b64decode(line.strip(), validate=True)
    except ValueError as e:  # binascii.Error (invalid base64) subclasses ValueError
        msg = f"Invalid base64 in minisign {what}"
        raise CatalogVerificationError(msg) from e
