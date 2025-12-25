# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Language toolchain for .NET projects."""

from __future__ import annotations

from hop3.core.protocols import BuildArtifact

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
        """Build the .NET application.

        .NET projects typically use a Procfile prebuild step to compile
        (e.g., 'prebuild: dotnet publish -c Release -o out').
        """
        return BuildArtifact(
            kind="dotnet",
            location=str(self.src_path),
            metadata={"app_name": self.app_name},
        )
