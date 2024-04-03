# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

from pathlib import Path

from hop3.util.backports import chdir
from hop3.util.console import log
from hop3.util.path import prepend_path
from hop3.util.settings import parse_settings

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
            self.shell("bundle install", env=env)

    def get_env(self) -> dict:
        path = prepend_path(
            [
                self.virtual_env / "bin",
                Path(self.app_name, ".bin"),
            ]
        )

        env = {
            "VIRTUAL_ENV": str(self.virtual_env),
            "PATH": path,
        }
        if self.env_file.exists():
            env.update(parse_settings(self.env_file, env))
        return env

    def make_virtual_env(self, env) -> None:
        if not self.virtual_env.exists():
            log("Building Ruby Application", level=5)
            self.virtual_env.mkdir(parents=True)
            self.shell("bundle config set --local path $VIRTUAL_ENV", env=env)
        else:
            log("Rebuilding Ruby Application", level=6)
