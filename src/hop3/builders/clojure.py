# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

import os
from pathlib import Path

from hop3.core.events import BuildEvent, CreatingVirtualEnv, emit
from hop3.util import shell
from hop3.util.backports import chdir
from hop3.util.console import log
from hop3.util.path import prepend_to_path
from hop3.util.settings import parse_settings

from .base import Builder


class ClojureBuilder(Builder):
    name = "Clojure"
    requirements = []  # TODO

    def accept(self):
        return self.is_leiningen_app or self.is_cli_app

    @property
    def is_leiningen_app(self) -> bool:
        return (self.app_path / "project.clj").exists()

    @property
    def is_cli_app(self) -> bool:
        return (self.app_path / "deps.edn").exists()

    def build(self) -> None:
        emit(CreatingVirtualEnv(self.app_name))
        self.virtual_env.mkdir(parents=True, exist_ok=True)

        emit(BuildEvent(self.app_name, "Building Clojure Application"))
        target_path = Path(self.app_path, "target")
        Path(target_path).mkdir(parents=True, exist_ok=True)
        self._build(self.get_env())

    def get_env(self) -> dict[str, str]:
        path = prepend_to_path(
            [
                Path(self.virtual_env, "bin"),
                Path(self.app_name, ".bin"),
            ]
        )

        env = {
            "VIRTUAL_ENV": self.virtual_env,
            "PATH": path,
        }

        if self.is_leiningen_app:
            lein_home = os.environ.get(
                "LEIN_HOME", os.path.join(os.environ["HOME"], ".lein")
            )
            env.update({"LEIN_HOME": lein_home})
        else:
            clj_config = os.environ.get(
                "CLJ_CONFIG", os.path.join(os.environ["HOME"], ".clojure")
            )
            env.update({"CLJ_CONFIG": clj_config})

        if Path(self.env_file).exists():
            env.update(parse_settings(self.env_file, env))

        return env

    def _build(self, env) -> None:
        log("Building Clojure Application", level=5)
        with chdir(self.app_path):
            if self.is_leiningen_app:
                shell("lein clean", env=env)
                shell("lein uberjar", env=env)
            else:
                shell("clojure -T:build release", env=env)
