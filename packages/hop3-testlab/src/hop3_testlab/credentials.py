# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Cloud-provider credential helpers: validation, redaction, key materialization.

Credentials themselves live in the DB (``models.Credential`` via
``CredentialsRepository``). This module holds the pure helpers around them: secret
columns must be redacted before display, and a credential's SSH private key must be
written to a 0600 file before the engine subprocess (paramiko) can use it as a key
path.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from hop3_testlab.config import TestlabConfig

if TYPE_CHECKING:
    from pathlib import Path


def looks_like_private_key(text: str) -> bool:
    """True if ``text`` carries a PEM/OpenSSH private-key header.

    Covers OpenSSH, RSA, EC and PKCS#8 (``BEGIN [OPENSSH|RSA|EC] PRIVATE KEY``);
    rejects empty input, public keys, and stray text. Not a cryptographic load — a
    real run proves usability and surfaces any failure loudly.
    """
    # ponytail: header check, not a full paramiko parse. Upgrade to a real load
    # (multi-type, passphrase) if silent bad keys ever bite.
    t = text.strip()
    return t.startswith("-----BEGIN ") and "PRIVATE KEY-----" in t


def redact(secret: str | None) -> str:
    """A short, stable fingerprint of a secret for the UI — never the secret."""
    if not secret:
        return "—"
    return "sha256:" + hashlib.sha256(secret.encode()).hexdigest()[:12]


def _sanitize(name: str) -> str:
    """A filesystem-safe leaf for a credential name."""
    return "".join(c if c.isalnum() or c in "-._" else "_" for c in name)


def materialize_key(name: str, private_key: str | None) -> Path | None:
    """Write a credential's private key to a 0600 file and return its path.

    The engine subprocess takes an SSH key *path* (``HOP3_TEST_SSH_KEY``), so the
    DB-stored key is written to ``KEYS_DIR/<name>.key`` (idempotent — rewritten only
    when the content differs). Returns ``None`` when the credential carries no key.
    """
    if not private_key or not private_key.strip():
        return None
    keys_dir = TestlabConfig.get_instance().KEYS_DIR
    keys_dir.mkdir(parents=True, exist_ok=True)
    path = keys_dir / f"{_sanitize(name)}.key"
    content = private_key.strip() + "\n"  # SSH keys need a trailing newline
    if not path.exists() or path.read_text() != content:
        path.write_text(content)
    path.chmod(0o600)
    return path
