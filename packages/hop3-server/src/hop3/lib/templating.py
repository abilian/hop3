# Copyright (c) 2023-2025, Abilian SAS
# Copyright (c) 2024 Stefane Fermigier
#
# SPDX-License-Identifier: Apache-2.0
"""Simple shell-style string interpolation."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

__all__ = ["expand_vars"]

if TYPE_CHECKING:
    from collections.abc import Mapping

PATTERN = r"\$(\w+|\{([^}]*)\})"


def expand_vars(
    template: str, env: Mapping[str, Any], default: str | None = None
) -> str:
    """
    Simple shell-style string interpolation.

    Note: This helper composes multi-line config fragments by substituting
    pre-rendered blocks as values (see e.g. ``NGINX_COMMON_FRAGMENT``
    wiring in plugins/proxy/nginx/_setup.py), so newlines in values are
    legitimate and cannot be rejected here. Defense against config
    injection therefore lives at the RPC boundary --- every user-supplied
    string that ends up in a rendered config must pass through
    ``hop3.core.identifiers`` validators first (see ``validate_hostname``,
    ``validate_app_name``, ``validate_env_var_key``). The only defensive
    check we keep here is for the NUL byte, which has no legitimate use in
    any text config we render and is a reliable injection signature.
    """

    def replace_var(match: re.Match[str]) -> str:
        value = env.get(
            match.group(2) or match.group(1),
            match.group(0) if default is None else default,
        )
        if isinstance(value, str) and "\x00" in value:
            msg = (
                f"Refusing to expand {match.group(0)!r}: substitution value "
                f"contains a NUL byte."
            )
            raise ValueError(msg)
        return value

    return re.sub(PATTERN, replace_var, template)
