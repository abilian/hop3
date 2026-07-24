# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures for the platform unit tests."""

from __future__ import annotations

import pytest

from hop3.platform import certificates


@pytest.fixture(autouse=True)
def _fast_self_signed_keys(monkeypatch):
    """
    Use a small RSA key for self-signed certs in tests.

    The self-signed key is intentionally 4096-bit in production, but generating
    one dominates these tests' runtime (~0.5s of openssl each). The tests only
    exercise the cert's *shape* (SAN present, covers its domain, 0600 key perms),
    not the key strength, so a 1024-bit key is enough and ~5x faster. Mirrors the
    root ``_fast_bcrypt`` fixture, which lowers the bcrypt work factor the same way.
    """
    monkeypatch.setattr(certificates, "SELF_SIGNED_KEY_BITS", 1024)
