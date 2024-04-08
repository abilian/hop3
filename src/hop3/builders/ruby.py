# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

from pathlib import Path

from hop3.core.env import Env
from hop3.core.events import CreatingVirtualEnv, InstallingVirtualEnv, emit
from hop3.util.backports import chdir
from hop3.util.path import prepend_to_path

from .base import Builder


class RubyBuilder(Builder):
    name = "Ruby"
    requirements = ["ruby", "gem", "bundle"]

    def accept(self) -> bool:
        return Path(self.app_path, "Gemfile").exists()

    def build(self) -> None:
        with chdir(self.app_path):
            env = self.get_env()
            self.make_virtual_env(env)

            emit(InstallingVirtualEnv(self.app_name))
            self.shell("bundle install", env=env)

    def get_env(self) -> Env:
        path = prepend_to_path(
            [
                self.virtual_env / "bin",
                self.app_path / ".bin",
            ]
        )

        env = Env(
            {
                "VIRTUAL_ENV": str(self.virtual_env),
                "PATH": path,
            }
        )
        env.parse_settings(self.env_file)
        return env

    def make_virtual_env(self, env: Env) -> None:
        if not self.virtual_env.exists():
            emit(CreatingVirtualEnv(self.app_name))
            self.virtual_env.mkdir(parents=True)
            self.shell("bundle config set --local path $VIRTUAL_ENV", env=env)
