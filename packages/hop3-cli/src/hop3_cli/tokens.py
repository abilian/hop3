# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""JWT token utilities."""

from __future__ import annotations

import re

from hop3_cli.exceptions import CliError

# JWT pattern: header.payload.signature, each base64url. Length bounds
# (20-500 per segment) reject short eyJ-prefixed false positives from
# log output without truncating real tokens.
JWT_PATTERN = re.compile(
    r"eyJ[A-Za-z0-9_-]{20,500}\.eyJ[A-Za-z0-9_-]{20,500}\.[A-Za-z0-9_-]{20,500}"
)


def extract_jwt(text: str) -> str | None:
    """
    Extract JWT token from text.

    Args:
        text: Text that may contain a JWT token

    Returns:
        The JWT token if found, None otherwise
    """
    match = JWT_PATTERN.search(text)
    return match.group(0) if match else None


def bearer_header(token: str) -> str:
    """
    The ``Authorization`` value for ``token``, refusing a malformed one.

    A token holding whitespace or a line break (two tokens read from one
    file, a pasted wrap) made the HTTP library reject the header with an
    error that quoted it, so the token was printed. The refusal names the
    problem and where the token comes from, never the token.
    """
    if not token or any(c.isspace() for c in token):
        msg = (
            "The API token contains whitespace or a line break, so it cannot be "
            "sent (it is not shown here). Check HOP3_API_TOKEN, or log in "
            "again: hop3 login"
        )
        raise CliError(msg)
    return f"Bearer {token}"
