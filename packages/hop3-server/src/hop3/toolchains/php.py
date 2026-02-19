# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Language toolchain for PHP projects."""

from __future__ import annotations

from subprocess import CalledProcessError
from typing import TYPE_CHECKING

from hop3.core.events import InstallingDependencies, PreparingBuildEnv, emit
from hop3.core.protocols import BuildArtifact
from hop3.lib import chdir, log

from ._base import LanguageToolchain

if TYPE_CHECKING:
    from hop3.core.env import Env


class PHPToolchain(LanguageToolchain):
    """Language toolchain for PHP projects.

    This provides methods to check for PHP project configurations,
    prepare the environment, and install necessary project dependencies
    using composer (if composer.json exists).

    Accepts projects with:
    - composer.json (Composer-based projects)
    - index.php (standard PHP entry point)
    - Any .php files in root (PHP applications with vendored dependencies)
    """

    name = "PHP"
    requirements = []  # Composer only required if composer.json exists  # noqa: RUF012

    def accept(self) -> bool:
        """Check if this is a PHP project.

        Accepts if any of these conditions are met:
        - composer.json exists (Composer-based project)
        - index.php exists (standard PHP entry point)
        - Any .php file exists in root directory
        """
        # Composer-based project
        if self.check_exists("composer.json"):
            return True

        # Standard PHP entry point
        if self.check_exists("index.php"):
            return True

        # Any PHP file in root
        php_files = list(self.src_path.glob("*.php"))
        return len(php_files) > 0

    def _has_composer(self) -> bool:
        """Check if this is a Composer-based project."""
        return self.check_exists("composer.json")

    def build(self) -> BuildArtifact:
        """Build the PHP project by installing dependencies and potentially
        running custom scripts."""
        log(f"Building PHP application '{self.app_name}'", level=1, fg="blue")

        with chdir(self.src_path):
            env = self.get_env()
            self.prepare_build_env(env)
            self.install_dependencies(env)

        return BuildArtifact(
            kind="php",
            location=str(self.src_path),
            metadata={"app_name": self.app_name},
        )

    def prepare_build_env(self, env: Env) -> None:
        """Prepare the environment for building the project, if necessary.

        This could involve setting up PHP-specific environment variables
        or toolchains.
        """
        emit(PreparingBuildEnv(self.app_name))
        log("Preparing PHP build environment...", level=2, fg="cyan")

    def install_dependencies(self, env: Env) -> None:
        """Install the PHP project's dependencies using composer (if applicable)."""
        if not self._has_composer():
            log(
                "No composer.json found - assuming vendored dependencies",
                level=2,
                fg="cyan",
            )
            return

        emit(InstallingDependencies(self.app_name))

        log("Installing PHP dependencies with composer...", level=2, fg="cyan")
        try:
            # Composer requires HOME to be set for cache directory
            self.shell(
                "composer install --no-interaction --optimize-autoloader",
                env=env.environ(),
            )
            log("PHP dependencies installed successfully", level=2, fg="green")
        except CalledProcessError as e:
            msg = (
                f"Failed to install dependencies for PHP project '{self.app_name}': {e}"
            )
            raise RuntimeError(msg) from e
