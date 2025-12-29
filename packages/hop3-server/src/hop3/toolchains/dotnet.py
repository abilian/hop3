# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Language toolchain for .NET projects."""

from __future__ import annotations

from hop3.core.protocols import BuildArtifact
from hop3.lib import log

from ._base import LanguageToolchain


class DotNetToolchain(LanguageToolchain):
    """Language toolchain for .NET projects.

    This is responsible for building .NET projects by checking for C# (.csproj)
    or F# (.fsproj) project files.
    """

    name = "DotNet"
    requirements = ["dotnet"]  # noqa: RUF012

    def accept(self) -> bool:
        """Check if the application has .NET project files (.csproj, .fsproj, .sln)."""
        patterns = ("*.csproj", "*.fsproj", "*.sln")
        return any(path for pattern in patterns for path in self.src_path.glob(pattern))

    def build(self) -> BuildArtifact:
        """Build the .NET application using dotnet CLI."""
        log(f"Building .NET application '{self.app_name}'", level=1, fg="blue")

        # Restore dependencies
        log("Restoring .NET dependencies...", level=2, fg="cyan")
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

        return BuildArtifact(
            kind="dotnet",
            location=str(self.src_path),
            metadata={"app_name": self.app_name},
        )
