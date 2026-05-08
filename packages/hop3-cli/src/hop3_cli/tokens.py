# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""JWT token utilities."""

from __future__ import annotations

import re

# JWT pattern: header.payload.signature, each base64url. Length bounds
# (20-500 per segment) reject short eyJ-prefixed false positives from
# log output without truncating real tokens.
JWT_PATTERN = re.compile(
    r"eyJ[A-Za-z0-9_-]{20,500}\.eyJ[A-Za-z0-9_-]{20,500}\.[A-Za-z0-9_-]{20,500}"
)


def extract_jwt(text: str) -> str | None:
    """Extract JWT token from text.

    Args:
        text: Text that may contain a JWT token

    Returns:
        The JWT token if found, None otherwise
    """
    match = JWT_PATTERN.search(text)
    return match.group(0) if match else None
