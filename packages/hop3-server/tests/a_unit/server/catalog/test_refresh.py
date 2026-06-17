# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the catalog refresh orchestration (ADR 049).

Network is stubbed: ``fetch_to`` is monkeypatched to drop a prebuilt signed
tarball, so the test exercises fetch→verify→publish→reload wiring offline.
"""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import tarfile

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hop3.server.catalog import refresh as refresh_module, service as service_module
from hop3.server.catalog.refresh import refresh_catalog
from hop3.server.catalog.service import CatalogService
from hop3.server.catalog.sync import CatalogSyncError

KEY_ID = b"\x01\x02\x03\x04\x05\x06\x07\x08"


@pytest.fixture(autouse=True)
def _reset_singleton():
    CatalogService.reset()
    yield
    CatalogService.reset()


def _pubkey_text(priv):
    pub = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return "untrusted comment: pub\n" + base64.b64encode(b"Ed" + KEY_ID + pub).decode()


def _sign(priv, message: bytes) -> str:
    payload = hashlib.blake2b(message, digest_size=64).digest()
    sig = priv.sign(payload)
    line1 = base64.b64encode(b"ED" + KEY_ID + sig).decode()
    tc = "file:catalog.tar.gz"
    line2 = base64.b64encode(priv.sign(sig + tc.encode())).decode()
    return f"untrusted comment: sig\n{line1}\ntrusted comment: {tc}\n{line2}\n"


def _build_signed_tarball(tmp_path, priv):
    src = tmp_path / "build"
    app = src / "nextcloud"
    app.mkdir(parents=True)
    (app / "hop3.toml").write_text(
        '[metadata]\nid = "nextcloud"\ntitle = "Nextcloud"\n'
    )
    index = {
        "format": 1,
        "serial": 1,
        "apps": [
            {
                "id": "nextcloud",
                "files": [
                    {
                        "path": "nextcloud/hop3.toml",
                        "sha256": hashlib.sha256(
                            (app / "hop3.toml").read_bytes()
                        ).hexdigest(),
                    }
                ],
            }
        ],
    }
    (src / "index.json").write_text(json.dumps(index))
    tarball = tmp_path / "catalog.tar.gz"
    with tarfile.open(tarball, "w:gz") as tar:
        for p in sorted(src.rglob("*")):
            tar.add(str(p), arcname=p.relative_to(src).as_posix(), recursive=False)
    return tarball, _sign(priv, tarball.read_bytes())


def test_refresh_without_key_fails_loud():
    with pytest.raises(CatalogSyncError, match="catalog signing public key"):
        refresh_catalog(public_key="")


def test_refresh_end_to_end(tmp_path, monkeypatch):
    priv = Ed25519PrivateKey.generate()
    prebuilt, sig_text = _build_signed_tarball(tmp_path, priv)
    catalog_root = tmp_path / "home" / "catalog"
    state_root = tmp_path / "home" / "catalog-state"

    def fake_fetch(url, dest, **kwargs):
        if url.endswith(".minisig"):
            dest.write_text(sig_text)
        else:
            shutil.copyfile(prebuilt, dest)

    monkeypatch.setattr(refresh_module, "fetch_to", fake_fetch)
    monkeypatch.setattr(service_module, "_default_catalog_dir", lambda: catalog_root)

    serial = refresh_catalog(
        source_url="https://hop3.dev/catalog/catalog.tar.gz",
        public_key=_pubkey_text(priv),
        catalog_root=catalog_root,
        state_root=state_root,
    )

    assert serial == 1
    svc = CatalogService.get_instance()
    assert svc.is_available()
    assert {a.id for a in svc.list_apps()} == {"nextcloud"}
