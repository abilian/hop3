# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the catalog verification core (ADR 049).

The ``minisign`` CLI is not assumed present, so we build format-correct signatures
with ``cryptography`` (the same primitive the verifier uses). Symmetry between a
homegrown signer and verifier is broken by the negative tests, which assert that
tampering anywhere in the chain is rejected.
"""

from __future__ import annotations

import base64
import hashlib
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hop3.server.catalog.verify import (
    CatalogVerificationError,
    sha256_file,
    verify_minisign,
    verify_tree_against_index,
)

KEY_ID = b"\x11\x22\x33\x44\x55\x66\x77\x88"


def _make_keypair():
    return Ed25519PrivateKey.generate()


def _public_key_text(priv: Ed25519PrivateKey, key_id: bytes = KEY_ID) -> str:
    pub = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    body = base64.b64encode(b"Ed" + key_id + pub).decode()
    return f"untrusted comment: minisign public key\n{body}\n"


def _sign(
    priv: Ed25519PrivateKey,
    message: bytes,
    *,
    prehashed: bool = True,
    key_id: bytes = KEY_ID,
    trusted_comment: str = "file:catalog.tar.gz",
) -> str:
    algo = b"ED" if prehashed else b"Ed"
    payload = (
        hashlib.blake2b(message, digest_size=64).digest() if prehashed else message
    )
    sig = priv.sign(payload)
    line1 = base64.b64encode(algo + key_id + sig).decode()
    global_sig = priv.sign(sig + trusted_comment.encode())
    line2 = base64.b64encode(global_sig).decode()
    return (
        f"untrusted comment: minisign signature\n{line1}\n"
        f"trusted comment: {trusted_comment}\n{line2}\n"
    )


# --- verify_minisign ---------------------------------------------------------


@pytest.mark.parametrize("prehashed", [True, False])
def test_verify_minisign_ok(prehashed):
    priv = _make_keypair()
    msg = b"the catalog tarball bytes"
    verify_minisign(msg, _sign(priv, msg, prehashed=prehashed), _public_key_text(priv))


def test_verify_minisign_tampered_message_fails():
    priv = _make_keypair()
    sig = _sign(priv, b"original")
    with pytest.raises(CatalogVerificationError, match="signature is invalid"):
        verify_minisign(b"tampered", sig, _public_key_text(priv))


def test_verify_minisign_wrong_key_fails():
    signer, attacker = _make_keypair(), _make_keypair()
    msg = b"content"
    sig = _sign(signer, msg)
    with pytest.raises(CatalogVerificationError, match="signature is invalid"):
        verify_minisign(msg, sig, _public_key_text(attacker))


def test_verify_minisign_key_id_mismatch_fails():
    priv = _make_keypair()
    msg = b"content"
    sig = _sign(priv, msg, key_id=b"\x00" * 8)
    with pytest.raises(CatalogVerificationError, match="key id does not match"):
        verify_minisign(msg, sig, _public_key_text(priv, key_id=KEY_ID))


def test_verify_minisign_tampered_trusted_comment_fails():
    priv = _make_keypair()
    msg = b"content"
    sig = _sign(priv, msg, trusted_comment="file:catalog.tar.gz")
    forged = sig.replace("file:catalog.tar.gz", "file:evil.tar.gz")
    with pytest.raises(CatalogVerificationError, match="trusted-comment"):
        verify_minisign(msg, forged, _public_key_text(priv))


def test_verify_minisign_truncated_signature_fails():
    priv = _make_keypair()
    msg = b"content"
    sig = _sign(priv, msg)
    # Corrupt the base64 sig body line.
    broken = sig.replace(sig.splitlines()[1], "QQ==")
    with pytest.raises(CatalogVerificationError):
        verify_minisign(msg, broken, _public_key_text(priv))


def test_verify_minisign_bad_base64_fails():
    priv = _make_keypair()
    with pytest.raises(CatalogVerificationError):
        verify_minisign(
            b"x", "untrusted comment: x\n!!!notb64!!!\n", _public_key_text(priv)
        )


def test_verify_minisign_trailing_garbage_rejected():
    # Strict 4-line parse: extra content a real `minisign -V` rejects must fail here.
    priv = _make_keypair()
    msg = b"content"
    sig = _sign(priv, msg) + "GARBAGE EXTRA LINE\n"
    with pytest.raises(CatalogVerificationError, match="expected 4 lines"):
        verify_minisign(msg, sig, _public_key_text(priv))


def test_verify_minisign_injected_comment_line_rejected():
    priv = _make_keypair()
    msg = b"content"
    lines = _sign(priv, msg).splitlines()
    lines.insert(1, "untrusted comment: injected")
    with pytest.raises(CatalogVerificationError, match="expected 4 lines"):
        verify_minisign(msg, "\n".join(lines) + "\n", _public_key_text(priv))


# --- verify_tree_against_index ----------------------------------------------


def _write(root, rel, content: bytes):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


def _index_for(root, paths):
    return {
        "format": 1,
        "serial": 1,
        "apps": [
            {
                "id": "app",
                "files": [
                    {"path": rel, "sha256": sha256_file(root / rel)} for rel in paths
                ],
            }
        ],
    }


def test_tree_matches_index_ok(tmp_path):
    _write(tmp_path, "nextcloud/hop3.toml", b"id='nextcloud'\n")
    _write(tmp_path, "nextcloud/readme.md", b"# Nextcloud\n")
    index = _index_for(tmp_path, ["nextcloud/hop3.toml", "nextcloud/readme.md"])
    # index.json on disk is allowed and ignored by the bijection check.
    _write(tmp_path, "index.json", json.dumps(index).encode())
    verify_tree_against_index(tmp_path, index)


def test_tree_missing_file_fails(tmp_path):
    _write(tmp_path, "app/hop3.toml", b"x")
    index = _index_for(tmp_path, ["app/hop3.toml"])
    (tmp_path / "app/hop3.toml").unlink()
    with pytest.raises(CatalogVerificationError, match="missing on disk"):
        verify_tree_against_index(tmp_path, index)


def test_tree_hash_mismatch_fails(tmp_path):
    _write(tmp_path, "app/hop3.toml", b"original")
    index = _index_for(tmp_path, ["app/hop3.toml"])
    (tmp_path / "app/hop3.toml").write_bytes(b"swapped after indexing")
    with pytest.raises(CatalogVerificationError, match="hash mismatch"):
        verify_tree_against_index(tmp_path, index)


def test_tree_extra_unlisted_file_fails(tmp_path):
    _write(tmp_path, "app/hop3.toml", b"x")
    index = _index_for(tmp_path, ["app/hop3.toml"])
    _write(tmp_path, "app/secret.sh", b"rm -rf /")  # injected, not in index
    with pytest.raises(
        CatalogVerificationError, match="not listed in the signed index"
    ):
        verify_tree_against_index(tmp_path, index)


def test_tree_path_traversal_in_index_fails(tmp_path):
    index = {"apps": [{"id": "x", "files": [{"path": "../evil", "sha256": "0" * 64}]}]}
    with pytest.raises(CatalogVerificationError, match="escapes the catalog"):
        verify_tree_against_index(tmp_path, index)


def test_tree_symlink_fails(tmp_path):
    _write(tmp_path, "app/hop3.toml", b"x")
    (tmp_path / "app" / "link").symlink_to(tmp_path / "app" / "hop3.toml")
    index = _index_for(tmp_path, ["app/hop3.toml"])
    with pytest.raises(CatalogVerificationError, match="symlink"):
        verify_tree_against_index(tmp_path, index)


def test_tree_malformed_index_entry_raises_verification_error(tmp_path):
    # Malformed-but-signed index must raise CatalogVerificationError, not a raw
    # KeyError/TypeError (honors the documented fail-loud contract).
    bad_indexes = [
        {"apps": "notalist"},
        {"apps": [{"files": "notalist"}]},
        {"apps": [{"files": [{"path": 123, "sha256": "0" * 64}]}]},
        {"apps": [{"files": [{"path": "a/b"}]}]},  # missing sha256
        {"apps": [{"files": [{"path": "a/b", "sha256": "tooshort"}]}]},
    ]
    for index in bad_indexes:
        with pytest.raises(CatalogVerificationError):
            verify_tree_against_index(tmp_path, index)


def test_tree_normalization_collision_rejected(tmp_path):
    index = {
        "apps": [
            {
                "files": [
                    {"path": "app/File", "sha256": "a" * 64},
                    {"path": "app/file", "sha256": "b" * 64},  # casefold-collides
                ]
            }
        ]
    }
    with pytest.raises(CatalogVerificationError, match="collide under"):
        verify_tree_against_index(tmp_path, index)
