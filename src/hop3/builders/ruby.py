# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from pathlib import Path

from hop3.core.env import Env
from hop3.core.events import CreatingVirtualEnv, InstallingVirtualEnv, emit
from hop3.util.backports import chdir
from hop3.util.path import prepend_to_path

from .base import Builder


class RubyBuilder(Builder):
    """Builds Ruby projects.

    Attributes
    ----------
        name (str): The name of the builder.
        requirements (list): The required tools for building with Ruby.

    """

    name = "Ruby"
    requirements = ["ruby", "gem", "bundle"]

    def accept(self) -> bool:
        """Check if a Gemfile exists in the specified app_path.

        Returns
        -------
            bool: True if a Gemfile exists, False otherwise.

        """
        return Path(self.app_path, "Gemfile").exists()

    def build(self) -> None:
        """Build the project by setting up a virtual environment and installing
        dependencies.
        """
        with chdir(self.app_path):
            env = self.get_env()
            self.make_virtual_env(env)

            emit(InstallingVirtualEnv(self.app_name))
            self.shell("bundle install", env=env)

    def get_env(self) -> Env:
        """Get the environment settings for the current configuration.

        Returns
        -------
            Env: An Env object containing the environment settings.

        """
        path = prepend_to_path(
            [
                self.virtual_env / "bin",
                self.app_path / ".bin",
            ],
        )

        env = Env(
            {
                "VIRTUAL_ENV": self.virtual_env,
                "PATH": path,
            },
        )
        env.parse_settings(self.env_file)
        return env

    def make_virtual_env(self, env: Env) -> None:
        """Create a virtual environment for the specified environment.

        Args:
        ----
            env (Env): The environment settings to use for creating the virtual environment.

        """
        if not self.virtual_env.exists():
            emit(CreatingVirtualEnv(self.app_name))
            self.virtual_env.mkdir(parents=True)
            self.shell("bundle config set --local path $VIRTUAL_ENV", env=env)
