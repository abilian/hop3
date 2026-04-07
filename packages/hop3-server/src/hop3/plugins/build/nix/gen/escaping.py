# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

"""Nix string escaping helpers.

Inside Nix multi-line strings (``'' ... ''``), ``${VAR}`` is interpolated
by Nix. To prevent this and pass the literal text through to the shell,
we escape ``${`` as ``''${``. Bare ``$VAR``, ``$(cmd)``, and ``$PWD`` are
not interpolation in Nix — they pass through literally.
"""

from __future__ import annotations

import re

_VAR_SUBST = re.compile(r"\$\{")


def nix_escape(s: str) -> str:
    """Escape a string for embedding in a Nix ``'' ... ''`` multi-line string.

    Only ``${VAR}`` needs escaping — becomes ``''${VAR}`` so that Nix emits
    the literal ``${VAR}`` at build time, which the shell then evaluates at
    runtime.

    >>> nix_escape("port: ${PORT}")
    "port: ''${PORT}"
    >>> nix_escape("$(date)")
    '$(date)'
    >>> nix_escape("$PWD")
    '$PWD'
    """
    return _VAR_SUBST.sub("''${", s)
