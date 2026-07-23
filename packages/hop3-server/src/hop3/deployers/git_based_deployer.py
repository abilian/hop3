# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import TYPE_CHECKING

from attrs import field, mutable

from hop3.lib import (
    Diagnosis,
    abort_with_diagnosis,
    chdir,
    check_binaries,
    log,
    shell,
)
from hop3.project.config import AppConfig
from hop3.run.spawn import spawn_app
from hop3.toolchains import TOOLCHAIN_CLASSES

if TYPE_CHECKING:
    from pathlib import Path

    from hop3.orm.app import App


__all__ = ["do_deploy"]


def do_deploy(
    app: App, *, deltas: dict[str, int] | None = None, newrev: str = ""
) -> None:
    """
    Deploy an application with optional configuration changes and revision
    update.

    Input:
    - app: An instance of the App class representing the application to be deployed.
    - deltas: An optional dictionary where keys are strings representing component names
              and values are integers representing the changes in configuration or scaling.
    - newrev: An optional string representing the new revision or version identifier to
              be deployed. Defaults to an empty string, indicating no revision change.
    """
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
            abort_with_diagnosis(
                Diagnosis(
                    component="Git deployer",
                    action="parse app configuration",
                    reason=(
                        f"app '{app_name}' has no worker processes declared "
                        "in Procfile or hop3.toml"
                    ),
                    hint=(
                        "Add at least a 'web' worker in Procfile (e.g., "
                        "'web: gunicorn app:app') or '[run].start' in hop3.toml"
                    ),
                    troubleshooting=[
                        "See docs/src/hop3-toml-reference.md for the schema",
                        f"hop3 app logs --app {app_name}",
                    ],
                )
            )

    def get_worker(self, name: str) -> str:
        return self.workers.get(name, "")

    def run_prebuild(self) -> None:
        """
        Execute the prebuild command for the worker.

        Raises:
        - Abort: Raises an Abort exception if the prebuild command returns a
          non-zero exit status, indicating an error during execution.
        """

        command = self.get_worker("prebuild")
        if not command:
            return

        log("Running prebuild.", level=2, fg="blue")
        retval = shell(command, cwd=self.src_path).returncode
        if retval:
            abort_with_diagnosis(
                Diagnosis(
                    component="Git deployer",
                    action="run prebuild command",
                    reason=(f"prebuild exited with status {retval}: {command}"),
                    hint=(
                        "Check the 'prebuild' entry in Procfile — it should "
                        "run cleanly in the app source directory"
                    ),
                    troubleshooting=[
                        f"hop3 app logs --app {self.app_name} --build",
                        f"cd {self.src_path} && {command}",
                    ],
                )
            )

    def run_build(self) -> None:
        """
        Execute the build process for an application.

        This determines the appropriate build worker or builder class to
        execute the build for an application. It first attempts to find
        a specific build worker and execute it. If no build worker is
        found, it iterates through a list of potential builder classes
        to find one that can handle the application and executes the
        build process.
        """
        # Attempt to find a specific build worker for the build process
        if build_worker := self.get_worker("build"):
            log("Running build.", level=2, fg="blue")
            retval = shell(build_worker, cwd=self.src_path).returncode
            if retval:
                abort_with_diagnosis(
                    Diagnosis(
                        component="Git deployer",
                        action="run build command",
                        reason=(f"build exited with status {retval}: {build_worker}"),
                        hint=(
                            "Check the 'build' entry in Procfile and make "
                            "sure all its dependencies are declared"
                        ),
                        troubleshooting=[
                            f"hop3 app logs --app {self.app_name} --build",
                            f"cd {self.src_path} && {build_worker}",
                        ],
                    )
                )
            return

        workers = self.workers
        builder_detected = False

        # Iterate through toolchain classes to find one that can handle the application
        for toolchain_class in TOOLCHAIN_CLASSES:
            toolchain = toolchain_class(self.app_name)
            if toolchain.accept():
                assert check_binaries(toolchain.requirements)
                log(f"{toolchain.name} app detected.", level=3, fg="green")
                toolchain.build()
                builder_detected = True

        # Check if specific worker combinations imply a generic or static app
        if "release" in workers and "web" in workers:
            log("Generic app detected.", level=3, fg="green")
            builder_detected = True

        elif "static" in workers:
            log("Static app detected.", level=3, fg="green")
            builder_detected = True

        # Raise an exception if no suitable builder is found
        if not builder_detected:
            abort_with_diagnosis(
                Diagnosis(
                    component="Git deployer",
                    action="detect application type",
                    reason=(
                        "no language toolchain accepted the app and no "
                        "generic/static layout was recognized"
                    ),
                    hint=(
                        "Ensure the app has one of: a recognized language "
                        "file (e.g., requirements.txt, package.json, Gemfile),"
                        " a Dockerfile, a 'static' worker, or both 'release'"
                        " and 'web' workers in Procfile"
                    ),
                    troubleshooting=[
                        "See docs/src/guide.md for supported languages",
                        f"ls {self.src_path}",
                    ],
                )
            )

    def run_postbuild(self) -> None:
        """
        Execute the postbuild command for a given worker.

        Raises:
        - Abort: Raises an Abort exception if the shell command returns a non-zero error value.
        """
        command = self.get_worker("postbuild")
        if not command:
            return

        log("Running postbuild command", level=2, fg="blue")
        result = shell(command, cwd=self.src_path)
        if result.returncode:
            abort_with_diagnosis(
                Diagnosis(
                    component="Git deployer",
                    action="run postbuild command",
                    reason=(
                        f"postbuild exited with status {result.returncode}: {command}"
                    ),
                    hint=(
                        "Check the 'postbuild' entry in Procfile — it runs "
                        "after the main build step completes"
                    ),
                    troubleshooting=[
                        f"hop3 app logs --app {self.app_name} --build",
                        f"cd {self.src_path} && {command}",
                    ],
                )
            )

    def _git_update(self, newrev: str) -> None:
        """
        Perform a git update by fetching the latest changes and resetting
        the repository to a specified revision.

        Input:
            newrev (str): The new revision hash to reset the git repository to.
            If empty, the reset step is skipped.

        Raises:
            RuntimeError: If any of the git commands fail, this will raise an exception
                          through the shell function which is expected to handle such errors.
        """
        env: dict[str, str] = {}  # Environment variables dictionary, currently empty
        with chdir(self.src_path):
            # Fetch the latest changes from the remote repository quietly
            shell("git fetch --quiet", env=env)
            if newrev:
                # Reset the repository to the specified revision
                shell(f"git reset --hard {newrev}", env=env)
            # Remove build artifacts left by the previous deploy. `git reset
            # --hard` only touches tracked files, so untracked/ignored output
            # (node_modules, .astro, .nuxt, dist, .next, target, vendor, …)
            # survives and a redeploy then builds on top of stale state — e.g.
            # `astro build`/`nuxt build` over a stale node_modules fails. Build
            # from a pristine tree every time so deploys are reproducible.
            # Single -f (not -ff) leaves registered submodules intact; they are
            # re-synced just below. -x also clears git-ignored files.
            shell("git clean -dfx", env=env)
            # Initialize the submodules
            shell("git submodule init", env=env)
            # Update the submodules to match the current commit
            shell("git submodule update", env=env)
