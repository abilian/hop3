# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pluggy

hookspec = pluggy.HookspecMarker("hop3")


@hookspec
def cli_commands() -> None:
    """Get CLI commands."""
