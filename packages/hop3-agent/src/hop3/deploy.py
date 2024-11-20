# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import TYPE_CHECKING

from attrs import field, mutable

from hop3.builders import BUILDER_CLASSES
from hop3.project.config import AppConfig
from hop3.run.spawn import spawn_app
from hop3.util import Abort, chdir, check_binaries, log, shell

if TYPE_CHECKING:
    from pathlib import Path

    from hop3.core.app import App


__all__ = ["do_deploy"]


def do_deploy(
    app: App, *, deltas: dict[str, int] | None = None, newrev: str = ""
) -> None:
    deployer = Deployer(app)
    deployer.deploy(deltas=deltas, newrev=newrev)


@mutable
class Deployer:
    app: App

    # Parsed and set during deployment
    workers: dict = field(factory=dict)
    config: AppConfig | None = None

    #
    # Properties
    #
    @property
    def app_path(self) -> Path:
        return self.app.app_path

    @property
    def src_path(self) -> Path:
        return self.app.src_path

    @property
    def app_name(self) -> str:
        return self.app.name

    #
    # Lifecycle
    #
    def deploy(self, *, deltas: dict[str, int] | None = None, newrev: str = "") -> None:
        """Deploy an app by resetting the work directory."""
        deltas = deltas or {}

        self.update(newrev)

        # Lifecycle of a build
        self.run_prebuild()
        self.run_build()
        self.run_postbuild()

        spawn_app(self.app, deltas)

    def update(self, newrev: str) -> None:
        app_name = self.app_name
        app_path = self.app_path

        self.app.check_exists()

        log(f"Deploying app '{app_name}'", level=0, fg="green")

        self._git_update(newrev)

        config = AppConfig.from_dir(app_path)
        self.config = config
        self.workers = config.workers

        if not self.workers:
            msg = f"Error: Procfile for app '{app_name}' (no workers)."
            raise Abort(msg)

    def get_worker(self, name: str) -> str:
        return self.workers.get(name, "")

    def run_prebuild(self) -> None:
        command = self.get_worker("prebuild")
        if not command:
            return

        log("Running prebuild.", level=2, fg="blue")
        retval = shell(command, cwd=self.src_path).returncode
        if retval:
            msg = f"prebuild failed due to command error value: {retval}"
            raise Abort(msg, retval)

    def run_build(self) -> None:
        if build_worker := self.get_worker("build"):
            log("Running build.", level=2, fg="blue")
            retval = shell(build_worker, cwd=self.src_path).returncode
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
            msg = "No app detected."
            raise Abort(msg)

    def run_postbuild(self) -> None:
        command = self.get_worker("postbuild")
        if not command:
            return

        log("Running postbuild command", level=2, fg="blue")
        retval = shell(command, cwd=self.src_path)
        if retval:
            msg = f"Exiting postbuild due to command error value: {retval}"
            raise Abort(msg)

    def _git_update(self, newrev: str) -> None:
        env: dict[str, str] = {}
        with chdir(self.src_path):
            shell("git fetch --quiet", env=env)
            if newrev:
                shell(f"git reset --hard {newrev}", env=env)
            shell("git submodule init", env=env)
            shell("git submodule update", env=env)
