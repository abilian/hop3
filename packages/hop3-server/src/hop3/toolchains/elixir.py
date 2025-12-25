# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Language toolchain for Elixir projects."""

from __future__ import annotations

from hop3.core.protocols import BuildArtifact

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
        """Build the Elixir application.

        Elixir projects typically use a Procfile prebuild step to compile
        (e.g., 'prebuild: mix deps.get && mix compile').
        """
        return BuildArtifact(
            kind="elixir",
            location=str(self.src_path),
            metadata={"app_name": self.app_name},
        )
