# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

# ruff:file-ignore[global-statement]
# `_encryptor` is a deliberate lazy-init singleton; migration to a Dishka
# provider is non-trivial because Hop3's commands resolve dataclass fields
# via a hand-rolled REPOSITORY_TYPES table in controllers/rpc.py rather than
# directly from the container. Tests reset the singleton via
# `reset_credential_encryptor()`.

"""Credential encryption and decryption using Fernet.

This module provides symmetric encryption of service credentials
(addon passwords, connection strings, API tokens) stored in the Hop3
database. The encryption key is derived from HOP3_SECRET_KEY with
PBKDF2-HMAC-SHA256.

Scheme versioning (Wave 3 security audit)
=========================================

- **v1** (legacy): global static salt ``b"hop3-credentials-v1"`` and
  100,000 PBKDF2 iterations. Records are stored without a version
  prefix (raw Fernet token).
- **v2** (current): install-specific 16-byte salt and 600,000 PBKDF2
  iterations (OWASP 2026 baseline for PBKDF2-HMAC-SHA256). Records are
  stored with a ``v2:`` prefix in front of the Fernet token so the
  decrypt path can dispatch to the correct key.

``encrypt()`` always writes v2. ``decrypt()`` auto-detects the version
from the prefix and falls back to v1 for legacy records. This makes the
upgrade transparent; operators can migrate stored records to v2 by
running ``hop3 admin reencrypt-credentials`` whenever they want, and 0.6
will be able to drop the v1 read path entirely.

Per-install salt
================

The v2 salt is read from ``HOP3_CREDENTIAL_SALT`` (hex or base64) when
set --- the installer should emit this on fresh installs alongside
``HOP3_SECRET_KEY``. When the env var is unset we derive a
deterministic per-install salt from ``HOP3_SECRET_KEY`` via a
domain-separated SHA-256, so existing installs automatically get a
unique salt without any operator action. Both paths defeat the shared
rainbow-table risk from the pre-v2 global-constant salt.

Example
=======

    >>> encryptor = get_credential_encryptor()
    >>> data = {"username": "user", "password": "secret"}
    >>> encrypted = encryptor.encrypt(data)
    >>> encrypted.startswith("v2:")
    True
    >>> encryptor.decrypt(encrypted) == data
    True
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os

from cryptography.fernet import Fernet

from hop3 import config as c

__all__ = [
    "SCHEME_V1_ITERATIONS",
    "SCHEME_V1_SALT",
    "SCHEME_V2_ITERATIONS",
    "SCHEME_V2_PREFIX",
    "CredentialEncryption",
    "get_credential_encryptor",
    "reset_credential_encryptor",
]

# v1 (legacy) --- kept for reads only.
SCHEME_V1_SALT = b"hop3-credentials-v1"
SCHEME_V1_ITERATIONS = 100_000

# v2 (current).
SCHEME_V2_PREFIX = "v2:"
SCHEME_V2_ITERATIONS = 600_000
_V2_SALT_ENV = "HOP3_CREDENTIAL_SALT"
_V2_SALT_DOMAIN = b"hop3-credentials-salt-v2|"
_V2_SALT_LENGTH = 16


def _derive_fernet_key(secret: bytes, salt: bytes, iterations: int) -> bytes:
    """PBKDF2-HMAC-SHA256 -> 32 bytes -> URL-safe base64 (Fernet format)."""
    key_material = hashlib.pbkdf2_hmac(
        hash_name="sha256",
        password=secret,
        salt=salt,
        iterations=iterations,
        dklen=32,
    )
    return base64.urlsafe_b64encode(key_material)


def _decode_configured_salt(raw: str) -> bytes:
    """Parse HOP3_CREDENTIAL_SALT. Accepts hex or base64; at least 16 bytes."""
    # Hex first (unambiguous) then base64.
    try:
        decoded = bytes.fromhex(raw)
    except ValueError:
        try:
            decoded = base64.b64decode(raw, validate=True)
        except (ValueError, binascii.Error) as e:
            msg = (
                f"{_V2_SALT_ENV} must be hex or base64-encoded "
                f"(got an unparseable value)."
            )
            raise ValueError(msg) from e
    if len(decoded) < _V2_SALT_LENGTH:
        msg = (
            f"{_V2_SALT_ENV} must decode to at least {_V2_SALT_LENGTH} bytes "
            f"(got {len(decoded)})."
        )
        raise ValueError(msg)
    return decoded[:_V2_SALT_LENGTH]


def _v2_salt(secret: bytes) -> bytes:
    """Per-install salt: configured env var, or deterministic from secret."""
    configured = os.environ.get(_V2_SALT_ENV, "").strip()
    if configured:
        return _decode_configured_salt(configured)
    # Fallback: derive per-install salt from HOP3_SECRET_KEY with a domain
    # separator so it is independent of the main KDF output. Cross-install
    # rainbow tables need to target each install's SECRET_KEY individually,
    # which is already required for full compromise.
    return hashlib.sha256(_V2_SALT_DOMAIN + secret).digest()[:_V2_SALT_LENGTH]


class CredentialEncryption:
    """Versioned Fernet-based credential encryptor.

    Writes v2 records; reads v1 or v2 records transparently. See module
    docstring for the scheme details.
    """

    def __init__(self) -> None:
        secret = c.HOP3_SECRET_KEY.encode("utf-8")
        # v2: per-install salt, 600k PBKDF2 iterations (OWASP 2026).
        self._fernet_v2 = Fernet(
            _derive_fernet_key(secret, _v2_salt(secret), SCHEME_V2_ITERATIONS)
        )
        # v1: legacy static salt + 100k iterations, kept for reads only so
        # pre-upgrade installs keep working until `hop3 admin
        # reencrypt-credentials` migrates them.
        self._fernet_v1 = Fernet(
            _derive_fernet_key(secret, SCHEME_V1_SALT, SCHEME_V1_ITERATIONS)
        )

    def encrypt(self, data: dict) -> str:
        """Encrypt a dict and return a v2-tagged string safe for DB storage.

        Args:
            data: JSON-serialisable dict of credentials.

        Returns:
            ``"v2:<fernet-token>"``. The prefix lets ``decrypt()`` route to
            the right key without embedding a version byte inside the
            Fernet token (whose format is owned by cryptography.Fernet).
        """
        json_data = json.dumps(data, sort_keys=True)
        token = self._fernet_v2.encrypt(json_data.encode("utf-8"))
        return SCHEME_V2_PREFIX + token.decode("utf-8")

    def decrypt(self, encrypted: str) -> dict:
        """Decrypt a v2 or v1 record and return the original dict.

        Raises:
            cryptography.fernet.InvalidToken: if the token is corrupted,
                tampered with, or was produced with a different key.
        """
        if encrypted.startswith(SCHEME_V2_PREFIX):
            token = encrypted[len(SCHEME_V2_PREFIX) :].encode("utf-8")
            fernet = self._fernet_v2
        else:
            token = encrypted.encode("utf-8")
            fernet = self._fernet_v1
        decrypted_bytes = fernet.decrypt(token)
        return json.loads(decrypted_bytes.decode("utf-8"))

    def is_legacy(self, encrypted: str) -> bool:
        """Whether a stored record is v1 (so the caller can upgrade it)."""
        return not encrypted.startswith(SCHEME_V2_PREFIX)


# Global singleton instance.
_encryptor: CredentialEncryption | None = None


def get_credential_encryptor() -> CredentialEncryption:
    """Get or create the global credential encryptor singleton."""
    global _encryptor
    if _encryptor is None:
        _encryptor = CredentialEncryption()
    return _encryptor


def reset_credential_encryptor() -> None:
    """Reset the singleton. Only for tests that mutate env/config state."""
    global _encryptor
    _encryptor = None
