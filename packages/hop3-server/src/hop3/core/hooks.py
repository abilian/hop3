# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Hook implementation marker for Hop3 plugins."""

from __future__ import annotations

import pluggy

# Create the hookspec and hookimpl decorators for plugins to use
hop3_hook_spec = pluggy.HookspecMarker("hop3")
hop3_hook_impl = pluggy.HookimplMarker("hop3")

# Convenience aliases
hookspec = hop3_hook_spec
hookimpl = hop3_hook_impl
