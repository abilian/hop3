# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Pinned catalog signing key (ADR 049 F3).

The public key the node verifies catalog signatures against is **compiled into the
release here** — not read from a file or env var at runtime — so its trust anchor
shares no write boundary with the catalog channel an attacker might control.

This is the public half of the official Hop3 catalog signing key (id
``fa06cb6b08e36105``). Its private counterpart is held offline by the release team
and never touches a node; the producer flow that signs the catalog with it is the
hop3-catalog repo's ``make publish`` (see ``docs/src/developers/catalog-publishing.md``).
A node with this key pinned verifies the official catalog at ``CATALOG_SOURCE_URL``
out of the box; operators can still point that URL at their own signed catalog and
recompile with their own key.

Key rotation (accepting a tuple of current+next keys, all compiled in) is the
documented hardening step — see ADR 049 "Hardening Path".
"""

from __future__ import annotations

# The minisign public key file text (comment line + base64 body). To rotate,
# regenerate with `hop3-catalog keygen` and paste the new catalog.pub here.
CATALOG_PUBLIC_KEY: str = (
    "untrusted comment: hop3 catalog public key fa06cb6b08e36105\n"
    "RWT6BstrCONhBUDJAARHbNOMa5eCDMdtoD/75ztsOTHYdVgyxDdQe4kf\n"
)


def get_catalog_public_key() -> str:
    """Return the compiled-in catalog public key ('' if not yet provisioned)."""
    return CATALOG_PUBLIC_KEY
