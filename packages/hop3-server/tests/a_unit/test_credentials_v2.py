# Copyright (c) 2023-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Wave 3 security audit: tests for the v2 credential-encryption scheme.

The legacy tests in ``test_credentials.py`` still pass --- they only
exercise the roundtrip contract, which is unchanged. The tests here
lock in the new behaviour explicitly: v2 prefix, v1 read-compat,
per-install salt derivation, env override, and singleton reset.
"""

from __future__ import annotations

import base64
import hashlib
import json

import pytest
from cryptography.fernet import Fernet, InvalidToken

from hop3 import config as c
from hop3.core.credentials import (
    SCHEME_V1_ITERATIONS,
    SCHEME_V1_SALT,
    SCHEME_V2_ITERATIONS,
    SCHEME_V2_PREFIX,
    CredentialEncryption,
    _derive_fernet_key,
    _v2_salt,
    get_credential_encryptor,
    reset_credential_encryptor,
)


@pytest.fixture(autouse=True)
def _reset_encryptor_singleton(monkeypatch):
    """Clear the env var and the global singleton between tests."""
    monkeypatch.delenv("HOP3_CREDENTIAL_SALT", raising=False)
    reset_credential_encryptor()
    yield
    reset_credential_encryptor()


def _make_v1_record(secret: str, data: dict) -> str:
    """Hand-craft a v1 record (no prefix, legacy salt, 100k iterations)."""
    key = _derive_fernet_key(
        secret.encode("utf-8"), SCHEME_V1_SALT, SCHEME_V1_ITERATIONS
    )
    fernet = Fernet(key)
    return fernet.encrypt(json.dumps(data).encode("utf-8")).decode("utf-8")


# ---------------------------------------------------------------------------
# v2 writes
# ---------------------------------------------------------------------------


def test_encrypt_emits_v2_prefix() -> None:
    encryptor = CredentialEncryption()
    token = encryptor.encrypt({"password": "secret"})
    assert token.startswith(SCHEME_V2_PREFIX)


def test_v2_roundtrip() -> None:
    encryptor = CredentialEncryption()
    data = {"username": "u", "password": "p", "port": 5432}
    assert encryptor.decrypt(encryptor.encrypt(data)) == data


def test_v2_iterations_are_at_owasp_2026_baseline() -> None:
    # Pin the constant: OWASP recommends 600k+ for PBKDF2-HMAC-SHA256.
    # If someone lowers this, the test fires.
    assert SCHEME_V2_ITERATIONS >= 600_000


def test_is_legacy_distinguishes_schemes() -> None:
    encryptor = CredentialEncryption()
    v2_token = encryptor.encrypt({"k": "v"})
    v1_token = _make_v1_record(c.HOP3_SECRET_KEY, {"k": "v"})
    assert encryptor.is_legacy(v2_token) is False
    assert encryptor.is_legacy(v1_token) is True


# ---------------------------------------------------------------------------
# v1 read compatibility
# ---------------------------------------------------------------------------


def test_decrypt_v1_record_still_works() -> None:
    """A legacy record (no prefix, 100k + static salt) must decrypt
    cleanly under the new encryptor, so the upgrade is zero-downtime."""
    data = {"username": "legacy", "password": "old-secret"}
    v1_token = _make_v1_record(c.HOP3_SECRET_KEY, data)
    encryptor = CredentialEncryption()
    assert encryptor.decrypt(v1_token) == data


def test_tampered_v1_record_fails() -> None:
    v1_token = _make_v1_record(c.HOP3_SECRET_KEY, {"k": "v"})
    tampered = v1_token[:-10] + "XXXXXXXXXX"
    with pytest.raises(InvalidToken):
        CredentialEncryption().decrypt(tampered)


def test_tampered_v2_record_fails() -> None:
    encryptor = CredentialEncryption()
    token = encryptor.encrypt({"k": "v"})
    tampered = token[:-10] + "XXXXXXXXXX"
    with pytest.raises(InvalidToken):
        encryptor.decrypt(tampered)


# ---------------------------------------------------------------------------
# Per-install salt
# ---------------------------------------------------------------------------


def test_v2_salt_fallback_is_deterministic_for_same_secret() -> None:
    """Without HOP3_CREDENTIAL_SALT the salt is derived from the secret
    deterministically, so the same install always gets the same salt."""
    secret = b"fake-install-secret-0000"
    assert _v2_salt(secret) == _v2_salt(secret)
    # Domain separator in the derivation means the salt is not the same
    # as the raw SHA-256 of the secret alone.
    assert _v2_salt(secret) != hashlib.sha256(secret).digest()[:16]


def test_v2_salt_fallback_differs_per_secret() -> None:
    """Different installs get different salts in the fallback path."""
    assert _v2_salt(b"install-A") != _v2_salt(b"install-B")


def test_env_salt_hex_override(monkeypatch) -> None:
    secret = b"same-secret"
    monkeypatch.setenv("HOP3_CREDENTIAL_SALT", "a" * 32)  # 16 bytes of 0xaa
    assert _v2_salt(secret) == bytes.fromhex("a" * 32)


def test_env_salt_base64_override(monkeypatch) -> None:
    secret = b"same-secret"
    raw = b"this-is-a-16byte"
    monkeypatch.setenv(
        "HOP3_CREDENTIAL_SALT", base64.b64encode(raw).decode("ascii")
    )
    assert _v2_salt(secret) == raw


def test_env_salt_too_short_raises(monkeypatch) -> None:
    monkeypatch.setenv("HOP3_CREDENTIAL_SALT", "deadbeef")  # only 4 bytes
    with pytest.raises(ValueError, match="at least 16 bytes"):
        _v2_salt(b"secret")


def test_env_salt_unparseable_raises(monkeypatch) -> None:
    monkeypatch.setenv("HOP3_CREDENTIAL_SALT", "not hex !!! not b64 !!!")
    with pytest.raises(ValueError, match="hex or base64"):
        _v2_salt(b"secret")


# ---------------------------------------------------------------------------
# Singleton reset
# ---------------------------------------------------------------------------


def test_reset_credential_encryptor_drops_singleton() -> None:
    first = get_credential_encryptor()
    reset_credential_encryptor()
    second = get_credential_encryptor()
    assert first is not second


def test_env_salt_change_visible_after_reset(monkeypatch) -> None:
    """If the operator rotates HOP3_CREDENTIAL_SALT they must call
    reset_credential_encryptor() (or restart) for new writes to use it.
    This test just confirms the reset works; not an automatic watcher."""
    encryptor_a = get_credential_encryptor()
    monkeypatch.setenv("HOP3_CREDENTIAL_SALT", "0" * 32)
    reset_credential_encryptor()
    encryptor_b = get_credential_encryptor()
    # Tokens from the two encryptors must not cross-decrypt.
    token_b = encryptor_b.encrypt({"k": "v"})
    with pytest.raises(InvalidToken):
        encryptor_a.decrypt(token_b)
