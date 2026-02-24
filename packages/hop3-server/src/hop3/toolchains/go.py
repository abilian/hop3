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

        If a custom build command is specified in hop3.toml [build] section,
        that command is run instead of the default go build. This allows
        projects using Makefiles (like Focalboard, Mattermost) to work.

        Otherwise, downloads dependencies and optionally compiles the application.
        For apps using 'go run' in their Procfile, we just download deps.
        For apps with a main package, we compile to a binary.
        """
        log(f"Building Go application '{self.app_name}'", level=1, fg="blue")

        # Check if custom build command is specified in hop3.toml
        custom_build = self._get_custom_build_command()
        if custom_build:
            log(f"Running custom build command: {custom_build}", level=2, fg="cyan")
            self.shell(custom_build)
            # Compiled binary - minimal runtime config (just workers)
            return self._make_build_artifact(
                kind="go",
                metadata={"custom_build": True},
            )

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

        # Compiled binary - minimal runtime config (just workers)
        return self._make_build_artifact(kind="go")

    def _get_custom_build_command(self) -> str | None:
        """Get custom build command from hop3.toml if specified.

        Returns the build command string if [build] build is set in hop3.toml,
        otherwise None.
        """
        if self.context is None:
            return None

        app_config = self.context.app_config
        hop3_config = app_config.get("hop3_config", {})
        build_section = hop3_config.get("build", {})
        build_cmd = build_section.get("build")

        if isinstance(build_cmd, list):
            return " && ".join(build_cmd) if build_cmd else None
        return build_cmd or None
