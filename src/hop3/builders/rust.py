# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from pathlib import Path
from subprocess import CalledProcessError

from hop3.core.env import Env
from hop3.core.events import CompilingProject, CreatingBuildEnv, emit
from hop3.util.backports import chdir

from .base import Builder


class RustBuilder(Builder):
    """A class representing a Rust builder, a type of Builder.

    Attributes
    ----------
        name (str): The name of the Rust builder.
        requirements (list): The list of requirements needed for building a Rust project.

    Methods
    -------
        - accept: Check if the application directory contains a Cargo.toml file, indicating it is a Rust project.
        - build:
        Build the Rust project using cargo.

        - prepare_build_env: Prepare the environment for building the project, if necessary. This could involve setting up Rust-specific environment variables or installing Rust toolchains.
        - compile_project:
        Compile the Rust project using cargo.

    """

    name = "Rust"
    requirements = ["cargo"]

    def accept(self) -> bool:
        """Check if the application directory contains a Cargo.toml file,
        indicating it is a Rust project.
        """
        return Path(self.app_path, "Cargo.toml").exists()

    def build(self) -> None:
        """Build the Rust project using cargo."""
        with chdir(self.app_path):
            env = self.get_env()
            self.prepare_build_env(env)
            self.compile_project()

    def prepare_build_env(self, env: Env) -> None:
        """Prepare the environment for building the project, if necessary.

        Notes
        -----
            This could involve setting up Rust-specific environment variables or installing Rust toolchains.

        """
        emit(CreatingBuildEnv(self.app_name))

        # TODO

    def compile_project(self) -> None:
        """Compile the Rust project using cargo."""
        emit(CompilingProject(self.app_name))

        try:
            self.shell("cargo build")
        except CalledProcessError as e:
            raise RuntimeError(f"Failed to compile Rust project '{self.app_name}': {e}")
