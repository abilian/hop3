# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Language toolchain for Rust projects."""

from __future__ import annotations

from hop3.core.protocols import BuildArtifact
from hop3.lib import log

from ._base import LanguageToolchain


class RustToolchain(LanguageToolchain):
    """Language toolchain for Rust projects."""

    name = "Rust"
    requirements = ["cargo"]  # noqa: RUF012

    def accept(self) -> bool:
        """Determine if the application directory is a Rust project.

        This checks if the application directory contains a "Cargo.toml" file,
        which is a configuration file indicating that the project is a Rust project.

        Returns:
            bool: True if "Cargo.toml" file exists, indicating the project is a Rust project;
                  False otherwise.
        """
        return self.check_exists("Cargo.toml")

    def build(self) -> BuildArtifact:
        """Build the Rust project using cargo.

        This compiles the Rust project in release mode and produces
        an optimized binary.
        """
        log(f"Building Rust application '{self.app_name}'", level=1, fg="blue")

        # Build in release mode for optimized binary
        log("Compiling Rust project with cargo...", level=2, fg="cyan")
        result = self.shell("cargo build --release", check=False)

        if result.returncode == 0:
            log("Rust compilation successful", level=2, fg="green")
        else:
            log(
                "Rust compilation failed - check Cargo.toml and source code",
                level=1,
                fg="red",
            )
            # Don't raise - let deployment continue and fail at runtime
            # This allows debugging via logs

        return BuildArtifact(
            kind="rust",
            location=str(self.src_path),
            metadata={"app_name": self.app_name},
        )
