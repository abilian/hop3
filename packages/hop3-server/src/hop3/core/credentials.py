# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Credential encryption and decryption using Fernet.

This module provides secure encryption/decryption of service credentials
using Fernet symmetric encryption. The encryption key is derived from
HOP3_SECRET_KEY using PBKDF2.

Security Notes:
    - Credentials are encrypted at rest in the database
    - HOP3_SECRET_KEY must be kept secret and never committed to version control
    - The same key must be used consistently (changing it will break decryption)
    - Key rotation is not currently supported but can be added later

Example:
    >>> encryptor = get_credential_encryptor()
    >>> data = {"username": "user", "password": "secret"}
    >>> encrypted = encryptor.encrypt(data)
    >>> decrypted = encryptor.decrypt(encrypted)
    >>> assert decrypted == data
"""

from __future__ import annotations

import base64
import hashlib
import json

from cryptography.fernet import Fernet

from hop3 import config as c


class CredentialEncryption:
    """Handles encryption/decryption of service credentials.

    Uses Fernet (symmetric encryption) with a key derived from HOP3_SECRET_KEY.
    Fernet provides authenticated encryption (AEAD) which ensures both
    confidentiality and integrity.

    The encryption key is derived using PBKDF2-HMAC-SHA256 with 100,000
    iterations, which is the industry standard for key derivation.
    """

    def __init__(self):
        """Initialize encryptor with key derived from HOP3_SECRET_KEY."""
        # Derive 32-byte key from HOP3_SECRET_KEY
        secret = c.HOP3_SECRET_KEY.encode("utf-8")

        # Use PBKDF2 for secure key derivation
        # Static salt is OK here since we have a single master key
        key_material = hashlib.pbkdf2_hmac(
            hash_name="sha256",
            password=secret,
            salt=b"hop3-credentials-v1",  # Version salt for future key rotation
            iterations=100000,
            dklen=32,  # Fernet requires 32 bytes
        )

        # Fernet requires base64-encoded key
        fernet_key = base64.urlsafe_b64encode(key_material)
        self.fernet = Fernet(fernet_key)

    def encrypt(self, data: dict) -> str:
        """Encrypt a dictionary of credentials.

        Args:
            data: Dictionary containing credentials (username, password, etc.)

        Returns:
            Base64-encoded encrypted string safe for database storage

        Example:
            >>> data = {"password": "secret123"}
            >>> encrypted = encryptor.encrypt(data)
            >>> assert "secret123" not in encrypted
        """
        json_data = json.dumps(data, sort_keys=True)
        encrypted_bytes = self.fernet.encrypt(json_data.encode("utf-8"))
        return encrypted_bytes.decode("utf-8")

    def decrypt(self, encrypted: str) -> dict:
        """Decrypt credentials back to dictionary.

        Args:
            encrypted: Base64-encoded encrypted string from database

        Returns:
            Dictionary containing decrypted credentials

        Raises:
            cryptography.fernet.InvalidToken: If decryption fails
                (wrong key, corrupted data, or tampering)

        Example:
            >>> encrypted = "gAAAAA..."
            >>> data = encryptor.decrypt(encrypted)
            >>> assert "password" in data
        """
        decrypted_bytes = self.fernet.decrypt(encrypted.encode("utf-8"))
        json_data = decrypted_bytes.decode("utf-8")
        return json.loads(json_data)


# Global singleton instance
_encryptor: CredentialEncryption | None = None


def get_credential_encryptor() -> CredentialEncryption:
    """Get or create the global credential encryptor.

    Returns a singleton instance to ensure consistent encryption key
    throughout the application lifecycle.

    Returns:
        CredentialEncryption: The global encryptor instance
    """
    global _encryptor
    if _encryptor is None:
        _encryptor = CredentialEncryption()
    return _encryptor
