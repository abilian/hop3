# Copyright (c) 2023-2024, Abilian SAS
# Copyright (c) 2024 Stefane Fermigier
#
# SPDX-License-Identifier: Apache-2.0

"""Simple shell-style string interpolation."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

PATTERN = r"\$(\w+|\{([^}]*)\})"


def expand_vars(template, env: Mapping[str, Any], default=None):
    """Simple shell-style string interpolation."""

    def replace_var(match):
        return env.get(
            match.group(2) or match.group(1),
            match.group(0) if default is None else default,
        )

    return re.sub(PATTERN, replace_var, template)
