# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Language toolchain for Rust projects."""

from __future__ import annotations

from hop3.core.protocols import BuildArtifact

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
        """Build the Rust project.

        Unlike some other toolchains, Rust projects typically use a Procfile
        prebuild step to compile (e.g., 'prebuild: cargo build --release').
        This method returns a stub artifact, similar to GoToolchain, and lets
        the Procfile prebuild handle the actual compilation.

        This approach works because:
        1. Rust compilation is slow and benefits from caching
        2. The Procfile prebuild step runs after package installation
        3. It allows the same pattern as Go projects
        """
        return BuildArtifact(
            kind="rust",
            location=str(self.src_path),
            metadata={"app_name": self.app_name},
        )
