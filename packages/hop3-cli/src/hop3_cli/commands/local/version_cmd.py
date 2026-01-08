# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Version command - show CLI version locally."""

from __future__ import annotations

from importlib.metadata import version as get_version
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hop3_cli.config import Config
    from hop3_cli.ui.rich_printer import RichPrinter


def handle_version(args: list[str], config: Config, printer: RichPrinter) -> bool:
    """Handle the version command - show CLI version locally."""
    try:
        cli_version = get_version("hop3-cli")
    except Exception:
        cli_version = "unknown"

    print(f"hop3-cli {cli_version}")
    return True
