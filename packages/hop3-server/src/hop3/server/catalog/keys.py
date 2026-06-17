# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Pinned catalog signing key (ADR 049 F3).

The public key the node verifies catalog signatures against is **compiled into the
release here** — not read from a file or env var at runtime — so its trust anchor
shares no write boundary with the catalog channel an attacker might control.

PROVISIONING: this ships **empty**. Catalog sync stays disabled and fails loud
until the Hop3 release process:

1. generates an offline minisign keypair (the private key never touches a node),
2. publishes a signed ``catalog.tar.gz`` + ``catalog.tar.gz.minisig``, and
3. bakes the *public* key text into ``CATALOG_PUBLIC_KEY`` below.

Key rotation (accepting a tuple of current+next keys, all compiled in) is the
documented hardening step — see ADR 049 "Hardening Path".
"""

from __future__ import annotations

# The minisign public key file text (or just its base64 body). Empty until
# provisioned — see the module docstring.
CATALOG_PUBLIC_KEY: str = ""


def get_catalog_public_key() -> str:
    """Return the compiled-in catalog public key ('' if not yet provisioned)."""
    return CATALOG_PUBLIC_KEY
