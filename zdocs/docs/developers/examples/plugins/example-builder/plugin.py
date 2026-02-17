# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Example Hop3 Builder Plugin.

This is a minimal example of a Hop3 plugin that provides a build strategy.
It demonstrates the core concepts of plugin development.
"""

from __future__ import annotations

from hop3.core.hooks import hookimpl
from .builder import ExampleBuilder


class ExamplePlugin:
    """Example plugin providing a simple Python build strategy.

    This plugin demonstrates:
    - How to structure a plugin class
    - How to implement hook methods
    - How to register build strategies

    Usage:
        This plugin would be registered either:
        1. Internally by placing in hop3.plugins package, or
        2. Externally via setuptools entry points
    """

    name = "example"

    @hookimpl
    def get_builders(self) -> list:
        """Return build strategies provided by this plugin.

        This hook is called by the plugin manager during initialization
        to collect all available build strategies.

        Returns:
            List containing ExampleBuilder class (not instance)
        """
        return [ExampleBuilder]


# Auto-register plugin instance when module is imported
# This is REQUIRED for the plugin to be discovered
plugin = ExamplePlugin()
