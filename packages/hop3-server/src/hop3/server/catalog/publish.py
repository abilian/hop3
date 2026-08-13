# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Catalog producer side (ADR 049): build + sign a ``catalog.tar.gz``.

The node consumes a signed tarball (``sync.py`` / ``verify.py``); this is the
matching publisher the Hop3 release process runs **offline**:

    hop3-catalog keygen   --out-dir keys/
    hop3-catalog publish  content/ --key keys/catalog.key --out-dir dist/

It emits ``index.json`` (the authoritative manifest — F1), a deterministic
``catalog.tar.gz`` driven by that index (so the tree is bijective with the index
by construction), and a detached minisign ``.minisig`` over the tarball bytes.

The signature/pubkey format is minisign's, so a published artifact verifies with
the stock ``minisign -V`` *and* with ``verify.verify_minisign``. The private-key
file format here is our own (a plain base64 line) — for a minisign-CLI signing
workflow, generate with ``minisign -G`` and sign with ``minisign -S`` instead,
then bake the ``.pub`` into ``keys.py``.

ponytail: signs with the already-present ``cryptography`` dep, no minisign binary.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import sys
import tarfile
import time
from dataclasses import dataclass
from operator import itemgetter
from pathlib import Path

import tomllib
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .policy import (
    PUBLISHABLE_STATUSES,
    CatalogSpecError,
    validate_catalog_app_files,
    validate_catalog_spec,
    validate_catalog_status,
)
from .verify import sha256_file

_ALGO_PREHASHED = b"ED"  # minisign: signature is over BLAKE2b-512 of the content
_INDEX_FILENAME = "index.json"
_IGNORED_NAMES = {"__pycache__", ".git", ".DS_Store"}


class PublishError(Exception):
    """Raised when a catalog cannot be built or signed."""


# --- key handling ------------------------------------------------------------


def generate_keypair() -> tuple[str, str]:
    """
    Return (public_key_text, secret_key_text) for a fresh signing key.

    The public file is minisign-compatible; the secret file is our own format
    (a single base64 line of ``key_id || raw_ed25519_seed``), readable by
    :func:`load_secret_key`.
    """
    key_id = os.urandom(8)
    priv = Ed25519PrivateKey.generate()
    pub_raw = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    priv_raw = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_body = base64.b64encode(b"Ed" + key_id + pub_raw).decode()
    sec_body = base64.b64encode(key_id + priv_raw).decode()
    kid = key_id.hex()
    pub_text = f"untrusted comment: hop3 catalog public key {kid}\n{pub_body}\n"
    sec_text = f"untrusted comment: hop3 catalog SECRET key {kid}\n{sec_body}\n"
    return pub_text, sec_text


def load_secret_key(text: str) -> tuple[bytes, Ed25519PrivateKey]:
    """Parse a secret-key file written by :func:`generate_keypair`."""
    body = [
        ln.strip()
        for ln in text.strip().splitlines()
        if ln.strip() and not ln.startswith("untrusted comment:")
    ]
    if not body:
        msg = "Empty catalog secret key file"
        raise PublishError(msg)
    raw = base64.b64decode(body[-1], validate=True)
    if len(raw) != 40:  # 8 (key id) + 32 (seed)
        msg = f"Malformed catalog secret key (got {len(raw)} bytes, want 40)"
        raise PublishError(msg)
    return raw[:8], Ed25519PrivateKey.from_private_bytes(raw[8:])


# --- index + tarball ---------------------------------------------------------


def find_app_dirs(content_dir: Path) -> list[tuple[Path, str]]:
    """
    Every app directory under ``content_dir``, with the status it declares.

    Two layouts are read, because a signed catalog outlives the tree that
    produced it and an older checkout must keep building:

    * ``<content_dir>/<app>/hop3.toml`` — flat, status unknown (``""``);
    * ``<content_dir>/<status>/<app>/hop3.toml`` — the maturity hierarchy of
      [ADR 059], where the *directory is the status* and nothing else records it.

    A directory holding neither a recipe nor app subdirectories is an error
    rather than something to skip: a typo'd status name would otherwise remove
    every app under it from the catalog silently, which is the failure this
    whole gate exists to prevent.
    """
    if not content_dir.is_dir():
        msg = f"Catalog content dir does not exist: {content_dir}"
        raise PublishError(msg)

    found: list[tuple[Path, str]] = []
    for entry in sorted(content_dir.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if (entry / "hop3.toml").exists():
            found.append((entry, ""))
            continue
        nested = [
            d
            for d in sorted(entry.iterdir())
            if d.is_dir() and not d.name.startswith(".") and (d / "hop3.toml").exists()
        ]
        if not nested:
            msg = (
                f"Catalog dir {entry.name!r} has no hop3.toml and holds no app "
                f"directories — a status directory must contain apps, and an app "
                f"directory must contain a recipe"
            )
            raise PublishError(msg)
        found += [(d, entry.name) for d in nested]
    return found


@dataclass(frozen=True, slots=True)
class IndexBuild:
    """
    The result of scanning a catalog source tree.

    ``sources`` maps each indexed path back to the file that produced it, which
    is where the source tree's status hierarchy is flattened away. ``excluded``
    lists ``(app_id, status)`` for recipes deliberately kept out of the artefact,
    so the caller can say which and why — being unpublished is a decision, and a
    decision nobody reports is indistinguishable from a bug.
    """

    index: dict
    sources: dict[str, Path]
    excluded: list[tuple[str, str]]


def build_index(content_dir: Path, serial: int) -> IndexBuild:
    """
    Build the signed-index manifest from a catalog source tree.

    Each app's spec is run through the coexistence gate (F7) *before* signing —
    the publish step is the primary place to reject a bad spec. Aborts loud on
    anything unexpected.

    Indexed paths are always ``<app-dir>/…`` regardless of where the recipe sits
    in the source tree: ADR 049 pins that shape as the boundary that does not
    change, and every deployed node's loader is written against it. The status
    hierarchy is a property of the source tree only.

    Recipes at a non-publishable status (ADR 059: ``alpha``, ``broken``,
    ``retired``) are kept out of the index and reported in
    :attr:`IndexBuild.excluded`. They are still validated first, so a recipe does
    not rot unnoticed while it waits to be promoted.
    """
    apps = []
    sources: dict[str, Path] = {}
    excluded: list[tuple[str, str]] = []
    for app_dir, status in find_app_dirs(content_dir):
        toml_path = app_dir / "hop3.toml"
        with toml_path.open("rb") as f:
            data = tomllib.load(f)
        app_id = data.get("metadata", {}).get("id", app_dir.name)
        published = not status or status in PUBLISHABLE_STATUSES
        try:
            validate_catalog_status(status, app_id)
            validate_catalog_spec(data, app_id)
            validate_catalog_app_files(app_dir, app_id, published=published)
        except CatalogSpecError as e:
            raise PublishError(str(e)) from e

        if not published:
            excluded.append((app_id, status))
            continue

        files = []
        for p in sorted(app_dir.rglob("*")):
            if not p.is_file() or _is_ignored(p):
                continue
            indexed = (Path(app_dir.name) / p.relative_to(app_dir)).as_posix()
            files.append({"path": indexed, "sha256": sha256_file(p)})
            sources[indexed] = p
        if not files:
            msg = f"Catalog app dir {app_dir.name!r} contains no files"
            raise PublishError(msg)
        entry: dict = {"id": app_id, "files": files}
        if status:
            entry["status"] = status
        apps.append(entry)

    if not apps:
        msg = f"No publishable catalog apps found under {content_dir}"
        raise PublishError(msg)
    # Sorted by id, not by traversal: with the hierarchy, traversal order is
    # status-then-app, and the index must not change because a recipe moved
    # between statuses.
    apps.sort(key=itemgetter("id"))
    return IndexBuild(
        index={"format": 1, "serial": serial, "apps": apps},
        sources=sources,
        excluded=sorted(excluded),
    )


def write_tarball(sources: dict[str, Path], index: dict, dest: Path) -> bytes:
    """
    Write a deterministic ``catalog.tar.gz`` containing exactly the indexed
    files plus ``index.json``, and return its bytes.

    Driving the tar off the index (not ``rglob``) guarantees the extracted tree
    is bijective with the index — the exact invariant the node enforces (F1).
    ``sources`` resolves each indexed path back to the file that produced it,
    which is where the source tree's status hierarchy is flattened away.
    """
    index_bytes = json.dumps(index, indent=2, sort_keys=True).encode()
    with tarfile.open(dest, "w:gz") as tar:
        tar.addfile(_member(_INDEX_FILENAME, len(index_bytes)), io.BytesIO(index_bytes))
        for app in index["apps"]:
            for entry in app["files"]:
                path = sources[entry["path"]]
                with path.open("rb") as f:
                    tar.addfile(_member(entry["path"], path.stat().st_size), f)
    return dest.read_bytes()


def sign_tarball(data: bytes, key_id: bytes, priv: Ed25519PrivateKey, name: str) -> str:
    """Return the detached minisign ``.minisig`` text over ``data`` (prehashed)."""
    prehash = hashlib.blake2b(data, digest_size=64).digest()
    sig = priv.sign(prehash)
    trusted_comment = f"file:{name}"
    global_sig = priv.sign(sig + trusted_comment.encode())
    line1 = base64.b64encode(_ALGO_PREHASHED + key_id + sig).decode()
    line2 = base64.b64encode(global_sig).decode()
    return (
        "untrusted comment: hop3 catalog signature\n"
        f"{line1}\n"
        f"trusted comment: {trusted_comment}\n"
        f"{line2}\n"
    )


def publish(
    content_dir: Path, secret_key_text: str, out_dir: Path, serial: int
) -> dict:
    """Build + sign a catalog. Returns ``{serial, tarball, signature, index}``."""
    key_id, priv = load_secret_key(secret_key_text)
    built = build_index(content_dir, serial)

    out_dir.mkdir(parents=True, exist_ok=True)
    tarball = out_dir / "catalog.tar.gz"
    sigfile = out_dir / "catalog.tar.gz.minisig"
    index_file = out_dir / _INDEX_FILENAME

    index_file.write_text(json.dumps(built.index, indent=2, sort_keys=True))
    data = write_tarball(built.sources, built.index, tarball)
    sigfile.write_text(sign_tarball(data, key_id, priv, tarball.name))
    return {
        "serial": serial,
        "tarball": tarball,
        "signature": sigfile,
        "index": index_file,
        "excluded": built.excluded,
    }


def _member(name: str, size: int) -> tarfile.TarInfo:
    """A normalized (reproducible, ownerless, non-setuid) tar member header."""
    ti = tarfile.TarInfo(name)
    ti.size = size
    ti.mtime = 0
    ti.mode = 0o644
    ti.uid = ti.gid = 0
    ti.uname = ti.gname = ""
    return ti


def _is_ignored(path: Path) -> bool:
    return any(part in _IGNORED_NAMES for part in path.parts) or path.suffix == ".pyc"


# --- CLI ---------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hop3-catalog", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    kg = sub.add_parser("keygen", help="generate a catalog signing keypair")
    kg.add_argument("--out-dir", type=Path, default=Path(), help="where to write keys")

    val = sub.add_parser(
        "validate", help="check specs (runs the coexistence gate, no signing)"
    )
    val.add_argument("content_dir", type=Path, help="dir of <app-id>/ dirs")

    pub = sub.add_parser("publish", help="build + sign a catalog tarball")
    pub.add_argument("content_dir", type=Path, help="dir of <app-id>/ dirs")
    pub.add_argument("--key", type=Path, required=True, help="secret key file")
    pub.add_argument("--out-dir", type=Path, default=Path("dist"))
    pub.add_argument(
        "--serial",
        type=int,
        default=int(time.time()),
        help="monotonic serial (must increase across releases; default: now)",
    )

    args = parser.parse_args(argv)
    try:
        if args.cmd == "keygen":
            return _run_keygen(args.out_dir)
        if args.cmd == "validate":
            return _run_validate(args.content_dir)
        return _run_publish(args.content_dir, args.key, args.out_dir, args.serial)
    except (PublishError, OSError) as e:
        print(f"hop3-catalog: {e}", file=sys.stderr)
        return 1


def _run_keygen(out_dir: Path) -> int:
    pub_text, sec_text = generate_keypair()
    out_dir.mkdir(parents=True, exist_ok=True)
    pub_path = out_dir / "catalog.pub"
    sec_path = out_dir / "catalog.key"
    pub_path.write_text(pub_text)
    sec_path.write_text(sec_text)
    sec_path.chmod(0o600)
    print(f"Wrote {pub_path} and {sec_path} (keep the .key offline + secret).")
    print("Bake the .pub body into hop3.server.catalog.keys.CATALOG_PUBLIC_KEY.")
    return 0


def _run_validate(content_dir: Path) -> int:
    # build_index runs the coexistence gate + structural checks and raises
    # PublishError on any problem (caught by main → exit 1). Serial is irrelevant
    # here, so pass 0.
    built = build_index(content_dir, serial=0)
    for app in built.index["apps"]:
        status = f"  [{app['status']}]" if app.get("status") else ""
        print(f"  ok  {app['id']}  ({len(app['files'])} files){status}")
    print(f"{len(built.index['apps'])} app(s) valid.")
    _report_excluded(built.excluded)
    return 0


def _report_excluded(excluded: list[tuple[str, str]]) -> None:
    """Name what will not ship, so its absence is a decision and not a surprise."""
    if not excluded:
        return
    by_status: dict[str, list[str]] = {}
    for app_id, status in excluded:
        by_status.setdefault(status, []).append(app_id)
    total = len(excluded)
    print(f"{total} app(s) validated but NOT published, by status:")
    for status in sorted(by_status):
        names = ", ".join(sorted(by_status[status]))
        print(f"  {status}: {names}")


def _run_publish(content_dir: Path, key: Path, out_dir: Path, serial: int) -> int:
    result = publish(content_dir, key.read_text(), out_dir, serial)
    print(f"Published catalog serial {result['serial']}:")
    print(f"  {result['tarball']}")
    print(f"  {result['signature']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
