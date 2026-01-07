# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Language toolchain for Rust projects."""

from __future__ import annotations

import shutil
from pathlib import Path

from hop3.core.protocols import BuildArtifact
from hop3.lib import log

from ._base import LanguageToolchain

# Common locations for cargo binary
CARGO_PATHS = [
    Path("/home/hop3/.cargo/bin/cargo"),
    Path.home() / ".cargo" / "bin" / "cargo",
    Path("/usr/local/bin/cargo"),
    Path("/usr/bin/cargo"),
]


def find_cargo() -> str:
    """Find the cargo binary.

    Checks common locations for rustup-installed cargo, then falls back
    to system PATH.

    Returns:
        Path to cargo binary, or just "cargo" if not found (let shell find it)
    """
    # Check known rustup locations first
    for path in CARGO_PATHS:
        if path.exists():
            return str(path)

    # Fall back to PATH lookup
    cargo = shutil.which("cargo")
    if cargo:
        return cargo

    # Last resort - let shell try to find it
    return "cargo"


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

        # Find cargo binary (may be in ~/.cargo/bin from rustup)
        cargo = find_cargo()
        log(f"Using cargo at: {cargo}", level=2, fg="cyan")

        # Build in release mode for optimized binary
        log("Compiling Rust project with cargo...", level=2, fg="cyan")
        result = self.shell(f"{cargo} build --release", check=False)

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
