# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Language toolchain for .NET projects."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.lib import log

from ._base import LanguageToolchain

if TYPE_CHECKING:
    from hop3.core.protocols import BuildArtifact


class DotNetToolchain(LanguageToolchain):
    """
    Language toolchain for .NET projects.

    This is responsible for building .NET projects by checking for C# (.csproj)
    or F# (.fsproj) project files.
    """

    name = "DotNet"
    requirements = ["dotnet"]  # ruff:ignore[mutable-class-default]

    def accept(self) -> bool:
        """Check if the application has .NET project files (.csproj, .fsproj, .sln)."""
        patterns = ("*.csproj", "*.fsproj", "*.sln")
        return any(path for pattern in patterns for path in self.src_path.glob(pattern))

    def build(self) -> BuildArtifact:
        """Build the .NET application using dotnet CLI."""
        log(f"Building .NET application '{self.app_name}'", level=1, fg="blue")

        # Restore dependencies
        log("Restoring .NET dependencies...", level=2, fg="cyan")
        if self._run_declared_build():
            return None
        self.shell("dotnet restore")

        # Build in Release mode
        log("Building .NET application...", level=2, fg="cyan")
        result = self.shell("dotnet build -c Release", check=False)

        if result.returncode == 0:
            log(".NET build successful", level=2, fg="green")
        else:
            log(
                ".NET build failed - check project files and source code",
                level=1,
                fg="red",
            )

        # Compiled .NET app - minimal runtime config (just workers)
        return self._make_build_artifact(kind="dotnet")
