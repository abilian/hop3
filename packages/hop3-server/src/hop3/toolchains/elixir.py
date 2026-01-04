# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Language toolchain for Elixir projects."""

from __future__ import annotations

import shutil

from hop3.core.protocols import BuildArtifact
from hop3.lib import log

from ._base import LanguageToolchain


class ElixirToolchain(LanguageToolchain):
    """Language toolchain for Elixir projects.

    This is responsible for building Elixir projects by checking for Mix
    (mix.exs) configuration files.
    """

    name = "Elixir"
    requirements = ["elixir", "mix"]  # noqa: RUF012

    def accept(self) -> bool:
        """Check if the application has Elixir/Mix configuration."""
        # Check for Mix project file
        return (self.src_path / "mix.exs").exists()

    def build(self) -> BuildArtifact:
        """Build the Elixir application using Mix.

        This fetches dependencies and compiles the application.
        """
        log(f"Building Elixir application '{self.app_name}'", level=1, fg="blue")

        # Clean build directories to avoid stale artifacts
        # This fixes issues with corrupted _build state on redeploys
        build_dir = self.src_path / "_build"
        deps_dir = self.src_path / "deps"
        if build_dir.exists():
            log("Cleaning previous build artifacts...", level=2, fg="cyan")
            shutil.rmtree(build_dir, ignore_errors=True)
        if deps_dir.exists():
            shutil.rmtree(deps_dir, ignore_errors=True)

        # Fetch dependencies
        log("Fetching Elixir dependencies...", level=2, fg="cyan")
        self.shell("mix deps.get")

        # Compile the application
        log("Compiling Elixir application...", level=2, fg="cyan")
        result = self.shell("mix compile", check=False)

        if result.returncode == 0:
            log("Elixir compilation successful", level=2, fg="green")
        else:
            log(
                "Elixir compilation failed - check mix.exs and source code",
                level=1,
                fg="red",
            )

        return BuildArtifact(
            kind="elixir",
            location=str(self.src_path),
            metadata={"app_name": self.app_name},
        )
