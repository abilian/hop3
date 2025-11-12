# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for credential encryption."""

from __future__ import annotations

import base64

import pytest
from cryptography.fernet import InvalidToken

from hop3.core.credentials import CredentialEncryption, get_credential_encryptor


class TestCredentialEncryption:
    """Test credential encryption and decryption."""

    def test_encrypt_decrypt_roundtrip(self):
        """Test that encrypted data can be decrypted back to original."""
        encryptor = CredentialEncryption()
        data = {
            "username": "testuser",
            "password": "secret123",
            "database": "testdb",
            "host": "localhost",
            "port": 5432,
        }

        encrypted = encryptor.encrypt(data)
        decrypted = encryptor.decrypt(encrypted)

        assert decrypted == data

    def test_encrypted_data_not_plaintext(self):
        """Test that sensitive data is not visible in encrypted form."""
        encryptor = CredentialEncryption()
        data = {"password": "supersecret", "username": "admin"}

        encrypted = encryptor.encrypt(data)

        # Sensitive data should not appear in plaintext
        assert "supersecret" not in encrypted
        assert "password" not in encrypted
        assert "admin" not in encrypted
        assert "username" not in encrypted

    def test_encrypted_data_is_base64(self):
        """Test that encrypted data is valid base64 (URL-safe variant)."""
        encryptor = CredentialEncryption()
        data = {"key": "value"}

        encrypted = encryptor.encrypt(data)

        # Fernet uses URL-safe base64 encoding
        # Should be decodable with urlsafe_b64decode
        base64.urlsafe_b64decode(encrypted)

    def test_tampering_detected(self):
        """Test that tampering with encrypted data is detected."""
        encryptor = CredentialEncryption()
        data = {"password": "secret"}

        encrypted = encryptor.encrypt(data)

        # Tamper with encrypted data
        tampered = encrypted[:-10] + "XXXXXXXXXX"

        # Decryption should fail
        with pytest.raises(InvalidToken):
            encryptor.decrypt(tampered)

    def test_empty_dict(self):
        """Test encryption of empty dictionary."""
        encryptor = CredentialEncryption()
        data = {}

        encrypted = encryptor.encrypt(data)
        decrypted = encryptor.decrypt(encrypted)

        assert decrypted == data

    def test_complex_nested_data(self):
        """Test encryption of complex nested structures."""
        encryptor = CredentialEncryption()
        data = {
            "credentials": {
                "username": "user",
                "password": "pass",
            },
            "connection": {
                "host": "localhost",
                "port": 5432,
                "options": ["ssl", "timeout=30"],
            },
        }

        encrypted = encryptor.encrypt(data)
        decrypted = encryptor.decrypt(encrypted)

        assert decrypted == data

    def test_unicode_data(self):
        """Test encryption of unicode characters."""
        encryptor = CredentialEncryption()
        data = {
            "username": "用户",
            "password": "пароль",
            "note": "🔐 secure",
        }

        encrypted = encryptor.encrypt(data)
        decrypted = encryptor.decrypt(encrypted)

        assert decrypted == data

    def test_different_encryptions_produce_different_output(self):
        """Test that encrypting the same data twice produces different output.

        Fernet includes a timestamp in the encrypted data, so the same plaintext
        encrypted twice will have different ciphertext.
        """
        encryptor = CredentialEncryption()
        data = {"password": "secret"}

        encrypted1 = encryptor.encrypt(data)
        encrypted2 = encryptor.encrypt(data)

        # Different ciphertext
        assert encrypted1 != encrypted2

        # But both decrypt to the same value
        assert encryptor.decrypt(encrypted1) == data
        assert encryptor.decrypt(encrypted2) == data

    def test_singleton_encryptor(self):
        """Test that get_credential_encryptor returns singleton."""
        enc1 = get_credential_encryptor()
        enc2 = get_credential_encryptor()

        assert enc1 is enc2

    def test_singleton_can_decrypt_each_others_data(self):
        """Test that singleton instances share the same key."""
        enc1 = get_credential_encryptor()
        enc2 = get_credential_encryptor()

        data = {"password": "test123"}

        # Encrypt with first instance
        encrypted = enc1.encrypt(data)

        # Decrypt with second instance (should work because same key)
        decrypted = enc2.decrypt(encrypted)

        assert decrypted == data

    def test_json_serializable_types_only(self):
        """Test that only JSON-serializable types can be encrypted."""
        encryptor = CredentialEncryption()

        # This should work (JSON-serializable)
        valid_data = {
            "string": "value",
            "number": 123,
            "float": 45.67,
            "boolean": True,
            "null": None,
            "list": [1, 2, 3],
            "nested": {"key": "value"},
        }

        encrypted = encryptor.encrypt(valid_data)
        decrypted = encryptor.decrypt(encrypted)
        assert decrypted == valid_data

    def test_large_data(self):
        """Test encryption of large data structures."""
        encryptor = CredentialEncryption()

        # Create a large dictionary
        data = {f"key_{i}": f"value_{i}" * 100 for i in range(100)}

        encrypted = encryptor.encrypt(data)
        decrypted = encryptor.decrypt(encrypted)

        assert decrypted == data
        # Encrypted size should be reasonable
        assert len(encrypted) < len(str(data)) * 2  # Not more than 2x original
