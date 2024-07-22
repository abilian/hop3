# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import os
from pathlib import Path

from hop3.core.env import Env
from hop3.core.events import BuildEvent, CreatingVirtualEnv, emit
from hop3.util.console import log
from hop3.util.path import prepend_to_path

from .base import Builder


class ClojureBuilder(Builder):
    """Builds Clojure projects (with either Leiningen or CLI).

    Attributes
    ----------
        name (str): The name of the Clojure builder.
        requirements (list): The list of requirements for the Clojure builder.

    Methods
    -------
        accept(): Returns True if the builder accepts the project.
        is_leiningen_app (property): Returns True if the project is a Leiningen app.
        is_cli_app (property): Returns True if the project is a CLI app.
        build(): Builds the Clojure application.
        get_env(): Returns the environment settings for building the application.
        _build(env): Builds the Clojure application with the specified environment.

    """

    name = "Clojure"
    requirements = []  # TODO

    def accept(self):
        """Check if the object is a Leiningen app or a CLI app.

        Returns
        -------
            bool: True if the object is a Leiningen app or a CLI app, False otherwise.

        """
        return self.is_leiningen_app or self.is_cli_app

    @property
    def is_leiningen_app(self) -> bool:
        """Check if the app is a Leiningen application.

        Returns
        -------
            bool: True if the app is a Leiningen application, False otherwise.

        """
        return (self.app_path / "project.clj").exists()

    @property
    def is_cli_app(self) -> bool:
        """Check if the application is a Clojure CLI app.

        Returns
        -------
            bool: True if the 'deps.edn' file exists in the app_path, False otherwise.

        """
        return (self.app_path / "deps.edn").exists()

    def build(self) -> None:
        """Build the Clojure application.

        This method creates a virtual environment, builds the Clojure application, and sets up the necessary directories.
        """
        emit(CreatingVirtualEnv(self.app_name))
        self.virtual_env.mkdir(parents=True, exist_ok=True)

        emit(BuildEvent(self.app_name, "Building Clojure Application"))
        target_path = Path(self.app_path, "target")
        Path(target_path).mkdir(parents=True, exist_ok=True)
        self._build(self.get_env())

    def get_env(self) -> Env:
        """Get the environment variables for the current setup.

        Returns
        -------
            Env: The environment variables based on the current setup.

        """
        path = prepend_to_path(
            [
                Path(self.virtual_env, "bin"),
                Path(self.app_name, ".bin"),
            ],
        )

        env = Env(
            {
                "VIRTUAL_ENV": self.virtual_env,
                "PATH": path,
            },
        )

        if self.is_leiningen_app:
            lein_home = os.environ.get(
                "LEIN_HOME",
                os.path.join(os.environ["HOME"], ".lein"),
            )
            env.update({"LEIN_HOME": lein_home})
        else:
            clj_config = os.environ.get(
                "CLJ_CONFIG",
                os.path.join(os.environ["HOME"], ".clojure"),
            )
            env.update({"CLJ_CONFIG": clj_config})

        env.parse_settings(self.env_file)

        return env

    def _build(self, env: Env) -> None:
        log("Building Clojure Application", level=5)
        if self.is_leiningen_app:
            self.shell("lein clean", env=env)
            self.shell("lein uberjar", env=env)
        else:
            self.shell("clojure -T:build release", env=env)
