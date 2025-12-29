# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Language toolchain for Go projects."""

from __future__ import annotations

from hop3.core.protocols import BuildArtifact
from hop3.lib import log

from ._base import LanguageToolchain


class GoToolchain(LanguageToolchain):
    """Language toolchain for Go projects.

    This is responsible for building Go projects by checking for Go
    dependencies or source files and then executing the necessary build
    commands.
    """

    name = "Go"
    requirements = ["go"]  # noqa: RUF012

    def accept(self) -> bool:
        """Check if the application has go dependencies or go source files."""
        # Check for go.mod (modern Go modules) or Godeps directory (legacy)
        # or raw .go files
        has_go_mod = (self.src_path / "go.mod").exists()
        has_godeps = (self.src_path / "Godeps").exists()
        has_go_files = len(list(self.src_path.glob("*.go"))) > 0

        return has_go_mod or has_godeps or has_go_files

    def build(self) -> BuildArtifact:
        """Build the Go application.

        This downloads dependencies and optionally compiles the application.
        For apps using 'go run' in their Procfile, we just download deps.
        For apps with a main package, we compile to a binary.
        """
        log(f"Building Go application '{self.app_name}'", level=1, fg="blue")

        # Download dependencies if go.mod exists
        if (self.src_path / "go.mod").exists():
            log("Downloading Go dependencies...", level=2, fg="cyan")
            self.shell("go mod download")

            # Also run go mod tidy to ensure go.sum is up to date
            log("Tidying Go modules...", level=2, fg="cyan")
            self.shell("go mod tidy")

        # Try to build the binary (optional - some apps use 'go run')
        # Check if there's a main.go or main package
        main_go = self.src_path / "main.go"
        if main_go.exists():
            log("Compiling Go application...", level=2, fg="cyan")
            # Build binary with the app name
            binary_name = self.app_name
            result = self.shell(f"go build -o {binary_name} .", check=False)
            if result.returncode == 0:
                log(f"Built binary: {binary_name}", level=2, fg="green")
            else:
                # Build failed, but that's OK if Procfile uses 'go run'
                log(
                    "Binary build skipped (app may use 'go run')",
                    level=2,
                    fg="yellow",
                )

        return BuildArtifact(
            kind="go",
            location=str(self.src_path),
            metadata={"app_name": self.app_name},
        )
