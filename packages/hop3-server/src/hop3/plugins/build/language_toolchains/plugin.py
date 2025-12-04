# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Plugin to register language toolchains."""

from __future__ import annotations

from hop3.core.hooks import hop3_hook_impl
from hop3.toolchains import TOOLCHAIN_CLASSES


class LanguageToolchainsPlugin:
    """Plugin that provides language toolchains for various languages.

    This plugin provides Level 2 toolchains (PythonToolchain, NodeToolchain, etc.)
    that are used by LocalBuilder to build applications.
    """

    name = "language-toolchains"

    @hop3_hook_impl
    def get_language_toolchains(self) -> list:
        """Return language toolchains for Python, Node, Ruby, etc.

        These toolchains are used by LocalBuilder (Level 1) to build
        language-specific components.
        """
        return TOOLCHAIN_CLASSES


# Auto-register plugin instance when module is imported
plugin = LanguageToolchainsPlugin()
