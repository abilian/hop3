# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Central resolution of the CLI config and cache directories.

A single chokepoint so the location honors the ``HOP3_CONFIG_DIR`` override
consistently. ``config.toml``, ``servers.toml``, ``state.toml`` and the
one-shot ADR-042 migration all derive from here, so relocating config (and
isolating it in tests) is a single lever rather than four.

The cache paths live here for the same reason: the completion command writes
them and the suggestion path reads them, and they used to be spelled out in
both places.
"""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_config_dir

APP_NAME = "hop3-cli"
APP_AUTHOR = "Abilian SAS"

#: Relocates config *and* cache together. Isolating a test run is one lever.
CONFIG_DIR_ENV = "HOP3_CONFIG_DIR"


def config_dir() -> Path:
    """
    Return the CLI config directory.

    Honors ``$HOP3_CONFIG_DIR`` when set (used both to relocate config and to
    isolate the test suite from the developer's real ``~/.config``). Otherwise
    falls back to the platform default (``~/.config/hop3-cli`` and equivalents)
    via ``platformdirs``.
    """
    override = _override()
    if override:
        return override

    return Path(user_config_dir(APP_NAME, APP_AUTHOR))


def cache_dir() -> Path:
    """
    Return the CLI cache directory (completion command and app-name lists).

    Honors ``$HOP3_CONFIG_DIR`` like ``config_dir``, so a test run is isolated by
    the same single lever; without that, the suggestion tests read and wrote the
    developer's own cache.

    The default stays ``~/.cache/hop3`` on every platform rather than following
    ``platformdirs``: the completion scripts this CLI *generates* read that path
    literally (see ``BASH_COMPLETION_SCRIPT``), so moving it would strand the
    scripts people have already installed. Change both together or neither.
    """
    override = _override()
    if override:
        return override / "cache"

    return Path.home() / ".cache" / "hop3"


def _override() -> Path | None:
    """``$HOP3_CONFIG_DIR``, when it is set to something."""
    value = os.environ.get(CONFIG_DIR_ENV, "")
    return Path(value) if value.strip() else None


def commands_cache_path() -> Path:
    """Plain-text command list, one space-separated name per line."""
    return cache_dir() / "commands.txt"


def apps_cache_path() -> Path:
    """Plain-text app-name list, one per line."""
    return cache_dir() / "apps.txt"
