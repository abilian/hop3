# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
"""=== CLI commands ===."""

from __future__ import annotations

from click import group
from devtools import debug

CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])


@group(context_settings=CONTEXT_SETTINGS)
def hop3() -> None:
    """Small, open source, extensible PaaS."""


@hop3.result_callback()
def cleanup(ctx) -> None:
    """Callback from command execution -- add debugging to taste."""
    debug(ctx)
