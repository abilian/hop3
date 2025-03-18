# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Builder for Rust projects."""

from __future__ import annotations

from subprocess import CalledProcessError
from typing import TYPE_CHECKING

from hop3.core.events import CompilingProject, CreatingBuildEnv, emit
from hop3.util import chdir

from ._base import Builder

if TYPE_CHECKING:
    from hop3.core.env import Env


class RustBuilder(Builder):
    """A class representing a Rust builder, a type of Builder."""

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

    def build(self) -> None:
        """Build the Rust project using cargo."""
        with chdir(self.src_path):
            env = self.get_env()
            self.prepare_build_env(env)
            self.compile_project()

    def prepare_build_env(self, env: Env) -> None:
        """Prepare the environment for building the project, if necessary.

        This sets up the necessary environment for building a project,
        potentially involving setting up Rust-specific environment variables or
        installing Rust toolchains.

        Input:
        - env (Env): The environment configuration object that dictates how the
          build process should be prepared.
        """
        emit(CreatingBuildEnv(self.app_name))

        # TODO

    def compile_project(self) -> None:
        """Compile the Rust project using cargo."""
        emit(CompilingProject(self.app_name))

        try:
            self.shell("cargo build")  # Attempt to build the project using cargo
        except CalledProcessError as e:
            # Raise a RuntimeError if the build process fails
            msg = f"Failed to compile Rust project '{self.app_name}': {e}"
            raise RuntimeError(msg)
