# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Central resolution of the CLI config directory.

A single chokepoint so the location honors the ``HOP3_CONFIG_DIR`` override
consistently. ``config.toml``, ``servers.toml``, ``state.toml`` and the
one-shot ADR-042 migration all derive from here, so relocating config (and,
crucially, isolating it in tests) is a single lever rather than four.
"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "hop3-cli"
APP_AUTHOR = "Abilian SAS"


def config_dir() -> Path:
    """Return the CLI config directory.

    Honors ``$HOP3_CONFIG_DIR`` when set (used both to relocate config and to
    isolate the test suite from the developer's real ``~/.config``). Otherwise
    falls back to the platform default (``~/.config/hop3-cli`` and equivalents)
    via ``platformdirs``.
    """
    override = os.environ.get("HOP3_CONFIG_DIR")
    if override and override.strip():
        return Path(override)
    from platformdirs import user_config_dir  # noqa: PLC0415

    return Path(user_config_dir(APP_NAME, APP_AUTHOR))
