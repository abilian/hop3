# Copyright (c) 2023-2024, Abilian SAS

from pathlib import Path
from subprocess import CalledProcessError

from hop3.builders.base import Builder
from hop3.core.env import Env
from hop3.core.events import CompilingProject, CreatingBuildEnv, emit
from hop3.util import shell
from hop3.util.backports import chdir


class RustBuilder(Builder):
    name = "Rust"
    requirements = ["cargo"]

    def accept(self) -> bool:
        """
        Check if the application directory contains a Cargo.toml file,
        indicating it is a Rust project.
        """
        return Path(self.app_path, "Cargo.toml").exists()

    def build(self) -> None:
        """
        Build the Rust project using cargo.
        """
        with chdir(self.app_path):
            env = self.get_env()
            self.prepare_build_env(env)
            self.compile_project()

    def prepare_build_env(self, env: Env) -> None:
        """
        Prepare the environment for building the project, if necessary.

        XXX: This could involve setting up Rust-specific environment variables or installing Rust toolchains.
        """
        emit(CreatingBuildEnv(self.app_name))

        # TODO

    def compile_project(self) -> None:
        """
        Compile the Rust project using cargo.
        """
        emit(CompilingProject(self.app_name))

        try:
            shell("cargo build")
        except CalledProcessError as e:
            raise RuntimeError(f"Failed to compile Rust project '{self.app_name}': {e}")
