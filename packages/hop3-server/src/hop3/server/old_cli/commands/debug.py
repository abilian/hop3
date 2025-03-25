# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""CLI commands to help debug the app."""

from __future__ import annotations

from pprint import pprint

from hop3.container import container
from hop3.lib.decorators import command


@command
class DebugCmd:
    """Print debug information."""

    def run(self):
        print("Wireup registry:")
        print()
        registry = container._registry  # noqa: SLF001

        print("Known interfaces:")
        pprint(registry.known_interfaces)
        print()

        print("Known implementations:")
        pprint(dict(registry.known_impls))
        print()

        print("Factory functions:")
        pprint(registry.factory_functions)
        print()

        print("Context:")
        pprint(registry.context)
        print()
