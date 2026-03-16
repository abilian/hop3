# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Generic toolchain for pre-built binaries and apps without build steps.

This toolchain is used when:
1. `toolchain = "generic"` or `toolchain = "none"` is explicitly set in hop3.toml
2. The app has a custom `build` command that handles everything
3. The app uses pre-built binaries that don't need compilation

The Generic toolchain does NOT auto-detect - it must be explicitly specified.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.lib import log

from ._base import LanguageToolchain

if TYPE_CHECKING:
    from hop3.core.protocols import BuildArtifact


class GenericToolchain(LanguageToolchain):
    """Generic toolchain for apps that don't need language-specific build steps.

    This toolchain accepts projects when explicitly specified via:
        [build]
        toolchain = "generic"  # or "none"

    It runs any custom build command specified in hop3.toml but doesn't
    perform any automatic dependency installation.
    """

    name = "Generic"
    requirements = []  # noqa: RUF012

    def accept(self) -> bool:
        """Accept only when explicitly specified via toolchain = 'generic' or 'none'.

        This toolchain does NOT auto-detect. It must be explicitly requested
        in hop3.toml to avoid accepting projects meant for other toolchains.
        """
        explicit_toolchain = self._get_explicit_toolchain()
        return explicit_toolchain in {"generic", "none"}

    def _get_explicit_toolchain(self) -> str | None:
        """Get explicitly specified toolchain from hop3.toml.

        Returns the toolchain name if [build] toolchain is set, otherwise None.
        """
        if self.context is None:
            return None

        app_config = self.context.app_config
        hop3_config = app_config.get("hop3_config", {})
        build_section = hop3_config.get("build", {})
        return build_section.get("toolchain")

    def build(self) -> BuildArtifact:
        """Build the project (run custom build command if specified).

        For generic projects, this may run a custom build command from
        hop3.toml or simply pass through without building.
        """
        log(f"Building generic application '{self.app_name}'", level=1, fg="blue")

        # Get custom build command if specified
        custom_build = self._get_custom_build_command()
        if custom_build:
            log(f"Running custom build command: {custom_build}", level=2, fg="cyan")
            self.shell(custom_build)
        else:
            log("No build command specified - assuming pre-built", level=2, fg="cyan")

        # Generic toolchain - minimal runtime config (just workers)
        return self._make_build_artifact(
            kind="generic",
            metadata={"toolchain": "generic"},
        )

    def _get_custom_build_command(self) -> str | None:
        """Get custom build command from hop3.toml if specified."""
        if self.context is None:
            return None

        app_config = self.context.app_config
        hop3_config = app_config.get("hop3_config", {})
        build_section = hop3_config.get("build", {})
        build_cmd = build_section.get("build")

        match build_cmd:
            case list() if build_cmd:
                return " && ".join(build_cmd)
            case str() if build_cmd:
                return build_cmd
            case _:
                return None
