# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Builder for Ruby projects."""

from __future__ import annotations

from hop3.core.env import Env
from hop3.core.events import CreatingVirtualEnv, InstallingVirtualEnv, emit
from hop3.util import chdir, prepend_to_path

from ._base import Builder


class RubyBuilder(Builder):
    """Builds Ruby projects.

    This is responsible for setting up and building Ruby projects. It
    checks for the existence of a Gemfile to confirm it is a Ruby
    project, sets up a virtual environment, and installs dependencies
    using Bundler.
    """

    name = "Ruby"
    requirements = ["ruby", "gem", "bundle"]  # noqa: RUF012

    def accept(self) -> bool:
        return self.check_exists("Gemfile")

    def build(self) -> None:
        with chdir(self.src_path):
            env = self.get_env()
            self.make_virtual_env(env)

            emit(InstallingVirtualEnv(self.app_name))
            self.shell("bundle install", env=env)

    def get_env(self) -> Env:
        path = prepend_to_path(
            [
                self.virtual_env / "bin",
                self.src_path / ".bin",
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
