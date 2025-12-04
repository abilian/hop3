# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Language toolchain for Clojure projects."""

from __future__ import annotations

import os
from pathlib import Path

from hop3.core.env import Env
from hop3.core.events import BuildEvent, CreatingVirtualEnv, emit
from hop3.core.protocols import BuildArtifact
from hop3.lib import log, prepend_to_path

from ._base import LanguageToolchain


class ClojureToolchain(LanguageToolchain):
    """Language toolchain for Clojure projects (with either Leiningen or CLI).

    This provides methods to build Clojure projects by determining if
    the project is a Leiningen app or a CLI Clojure app, setting up the
    necessary environment, and executing the build process. It extends
    the functionality of the Builder class.
    """

    name = "Clojure"
    # TODO
    requirements = []  # noqa: RUF012

    def accept(self) -> bool:
        """Check if the object is a Leiningen app or a CLI Clojure app."""
        return self.check_exists(["project.clj", "deps.edn"])

    @property
    def is_leiningen_app(self) -> bool:
        """Check if the app is a Leiningen application.

        Returns
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

    def build(self) -> BuildArtifact:
        """Build the Clojure application.

        This creates a virtual environment, builds the Clojure
        application, and sets up the necessary directories.
        """
        emit(CreatingVirtualEnv(self.app_name))
        self.virtual_env.mkdir(parents=True, exist_ok=True)

        emit(BuildEvent(self.app_name, "Building Clojure Application"))
        target_path = self.src_path / "target"
        target_path.mkdir(parents=True, exist_ok=True)
        self._build(self.get_env())

        return BuildArtifact(
            kind="clojure",
            location=str(target_path),
            metadata={
                "app_name": self.app_name,
                "is_leiningen": self.is_leiningen_app,
            },
        )

    def get_env(self) -> Env:
        """Get the environment variables for the current setup."""
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

        if self.is_leiningen_app:
            lein_home = os.environ.get("LEIN_HOME", str(Path.home() / ".lein"))
            env["LEIN_HOME"] = lein_home
        else:
            clj_config = os.environ.get("CLJ_CONFIG", str(Path.home() / ".clojure"))
            env["CLJ_CONFIG"] = clj_config

        env.parse_settings(self.env_file)

        return env

    def _build(self, env: Env) -> None:
        log("Building Clojure Application", level=3)
        if self.is_leiningen_app:
            self.shell("lein clean", env=env)
            self.shell("lein uberjar", env=env)
        else:
            self.shell("clojure -T:build release", env=env)
