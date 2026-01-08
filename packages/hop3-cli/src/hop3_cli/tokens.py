# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""JWT token utilities."""

from __future__ import annotations

import re

# JWT token pattern: 3 base64url segments separated by dots
# Format: header.payload.signature (each segment starts with eyJ for JSON)
JWT_PATTERN = re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")


def extract_jwt(text: str) -> str | None:
    """Extract JWT token from text.

    Args:
        text: Text that may contain a JWT token

    Returns:
        The JWT token if found, None otherwise
    """
    match = JWT_PATTERN.search(text)
    return match.group(0) if match else None
