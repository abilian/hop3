# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

"""=== CLI commands ===."""

from __future__ import annotations

from click import group
from devtools import debug

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


@group(context_settings=CONTEXT_SETTINGS)
def hop3() -> None:
    """Small, open source, extensible PaaS."""


@hop3.result_callback()
def cleanup(ctx) -> None:
    """Callback from command execution -- add debugging to taste."""
    debug(ctx)
