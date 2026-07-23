# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Language toolchain for Rust projects."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from hop3.lib import log

from ._base import LanguageToolchain

if TYPE_CHECKING:
    from hop3.core.protocols import BuildArtifact

# Common locations for cargo binary
CARGO_PATHS = [
    Path("/home/hop3/.cargo/bin/cargo"),
    Path.home() / ".cargo" / "bin" / "cargo",
    Path("/usr/local/bin/cargo"),
    Path("/usr/bin/cargo"),
]


def find_cargo() -> str:
    """
    Find the cargo binary.

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
    requirements = ["cargo"]  # ruff:ignore[mutable-class-default]

    def accept(self) -> bool:
        """
        Determine if the application directory is a Rust project.

        This checks if the application directory contains a "Cargo.toml" file,
        which is a configuration file indicating that the project is a Rust project.

        Returns:
            bool: True if "Cargo.toml" file exists, indicating the project is a Rust project;
                  False otherwise.
        """
        return self.check_exists("Cargo.toml")

    def build(self) -> BuildArtifact:
        """
        Build the Rust project using cargo.

        By default, runs `cargo build --release`. If the app declares
        `[build].build` in hop3.toml (e.g., to add `--features` flags),
        that command runs instead — matching the behaviour of every
        other toolchain (Go, Node, PHP, Generic) that already honours
        the custom-build field.

        Raises RuntimeError on cargo failure. Silently continuing the
        deploy past a failed build leaves the operator with a useless
        "target/release/<binary>: No such file or directory" at runtime
        instead of the real compiler error.
        """
        log(f"Building Rust application '{self.app_name}'", level=1, fg="blue")

        cargo = find_cargo()
        log(f"Using cargo at: {cargo}", level=2, fg="cyan")

        custom_build = self._get_custom_build_command()
        if custom_build:
            log(f"Running custom build command: {custom_build}", level=2, fg="cyan")
            build_cmd = custom_build
        else:
            build_cmd = f"{cargo} build --release"
            log("Compiling Rust project with cargo...", level=2, fg="cyan")

        result = self.shell(build_cmd, check=False)

        if result.returncode != 0:
            msg = (
                f"Rust compilation failed (exit {result.returncode}). "
                f"Command: {build_cmd}. "
                "Check Cargo.toml, missing system libraries (libssl-dev, "
                "libsqlite3-dev, pkg-config), or the app's build.log."
            )
            log(msg, level=1, fg="red")
            raise RuntimeError(msg)

        log("Rust compilation successful", level=2, fg="green")
        return self._make_build_artifact(kind="rust")
