# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import os
from pathlib import Path

from hop3.builders import BUILDER_CLASSES
from hop3.project.config import AppConfig
from hop3.run.spawn import spawn_app
from hop3.system.constants import APP_ROOT, LOG_ROOT
from hop3.util import check_binaries, shell
from hop3.util.backports import chdir
from hop3.util.console import Abort, log

# Will be removed

__all__ = ["do_deploy"]


def do_deploy(app_name: str, deltas: dict[str, int] | None = None, newrev=None) -> None:
    deployer = Deployer(app_name)
    deployer.deploy(deltas, newrev)


class Deployer:
    app_name: str
    workers: dict
    config: AppConfig

    def __init__(self, app_name: str) -> None:
        self.app_name = app_name
        self.workers = {}

    @property
    def app_path(self) -> Path:
        return Path(APP_ROOT, self.app_name)

    def deploy(self, deltas: dict[str, int] | None = None, newrev=None) -> None:
        """Deploy an app by resetting the work directory."""
        deltas = deltas or {}
        app_name = self.app_name

        self.update(newrev)

        # Lifecycle of a build
        self.run_prebuild()
        self.run_build()
        self.run_postbuild()

        spawn_app(app_name, deltas)

    def update(self, newrev) -> None:
        app_name = self.app_name
        app_path = self.app_path

        if not app_path.exists():
            raise Abort(f"Error: app '{app_name}' not found.")

        log_path = Path(LOG_ROOT, self.app_name)
        if not log_path.exists():
            os.makedirs(log_path)

        log(f"Deploying app '{app_name}'", level=5, fg="green")

        self._git_update(newrev)

        config = AppConfig.from_dir(app_path)
        self.config = config
        self.workers = config.workers

        if not self.workers:
            raise Abort(f"Error: Invalid Procfile for app '{app_name}'.")

    def get_worker(self, name: str) -> str:
        return self.workers.get(name, "")

    def run_prebuild(self) -> None:
        command = self.get_worker("prebuild")
        if not command:
            return

        log("Running prebuild.", level=5, fg="blue")
        retval = shell(command, cwd=self.app_path).returncode
        if retval:
            raise Abort(f"prebuild failed due to command error value: {retval}", retval)

    def run_build(self) -> None:
        if build_worker := self.get_worker("build"):
            log("Running build.", level=5, fg="blue")
            retval = shell(build_worker, cwd=self.app_path).returncode
            if retval:
                msg = f"Build failed due to command error value: {retval}"
                raise Abort(msg, retval)
            return

        workers = self.workers
        builder_detected = False

        for builder_class in BUILDER_CLASSES:
            builder = builder_class(self.app_name)
            if builder.accept():
                assert check_binaries(builder.requirements)
                log(f"{builder.name} app detected.", level=5, fg="green")
                builder.build()
                builder_detected = True

        # FIXME
        if "release" in workers and "web" in workers:
            log("Generic app detected.", level=5, fg="green")
            builder_detected = True

        elif "static" in workers:
            log("Static app detected.", level=5, fg="green")
            builder_detected = True

        if not builder_detected:
            raise Abort("No app detected.")

    def run_postbuild(self) -> None:
        app_path = self.app_path

        command = self.get_worker("postbuild")
        if not command:
            return

        log("Releasing", level=5, fg="blue")
        retval = shell(command, cwd=app_path)
        if retval:
            raise Abort(f"Exiting postbuild due to command error value: {retval}")

    def _git_update(self, newrev) -> None:
        app_path = self.app_path
        # env = {"GIT_WORK_DIR": app_path}
        env: dict[str, str] = {}
        with chdir(app_path):
            shell("git fetch --quiet", env=env)
            if newrev:
                shell(f"git reset --hard {newrev}", env=env)
            shell("git submodule init", env=env)
            shell("git submodule update", env=env)
