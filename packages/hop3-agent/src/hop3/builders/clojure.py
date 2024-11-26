# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Builder for Clojure projects."""

from __future__ import annotations

import os
from pathlib import Path

from hop3.core.env import Env
from hop3.core.events import BuildEvent, CreatingVirtualEnv, emit
from hop3.util import log, prepend_to_path

from ._base import Builder


class ClojureBuilder(Builder):
    """Builds Clojure projects (with either Leiningen or CLI)."""

    name = "Clojure"
    # TODO
    requirements = []  # noqa: RUF012

    def accept(self):
        """Check if the object is a Leiningen app or a CLI Clojure app.

        Returns
        -------
            bool: True if the object is a Leiningen app or a CLI Clojure app, False otherwise.

        """
        return self.check_exists(["project.clj", "deps.edn"])

    @property
    def is_leiningen_app(self) -> bool:
        """Check if the app is a Leiningen application.

        Returns
        -------
            bool: True if the app is a Leiningen application, False otherwise.

        """
        return (self.src_path / "project.clj").exists()

    @property
    def is_cli_app(self) -> bool:
        """Check if the application is a Clojure CLI app.

        Returns
        -------
            bool: True if the 'deps.edn' file exists in the app_path, False otherwise.

        """
        return (self.src_path / "deps.edn").exists()

    def build(self) -> None:
        """Build the Clojure application.

        This method creates a virtual environment, builds the Clojure application, and sets up the necessary directories.
        """
        emit(CreatingVirtualEnv(self.app_name))
        self.virtual_env.mkdir(parents=True, exist_ok=True)

        emit(BuildEvent(self.app_name, "Building Clojure Application"))
        target_path = self.src_path / "target"
        target_path.mkdir(parents=True, exist_ok=True)
        self._build(self.get_env())

    def get_env(self) -> Env:
        """Get the environment variables for the current setup.

        Returns
        -------
            Env: The environment variables based on the current setup.

        """
        path = prepend_to_path(
            [
                self.virtual_env / "bin",
                # FIXME: probably bad
                Path(self.app_name) / ".bin",
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
            env["LEIN_HOME"] = lein_home
        else:
            clj_config = os.environ.get(
                "CLJ_CONFIG",
                os.path.join(os.environ["HOME"], ".clojure"),
            )
            env["CLJ_CONFIG"] = clj_config

        env.parse_settings(self.env_file)

        return env

    def _build(self, env: Env) -> None:
        log("Building Clojure Application", level=5)
        if self.is_leiningen_app:
            self.shell("lein clean", env=env)
            self.shell("lein uberjar", env=env)
        else:
            self.shell("clojure -T:build release", env=env)
