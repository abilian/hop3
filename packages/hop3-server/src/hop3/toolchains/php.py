# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Language toolchain for PHP projects."""

from __future__ import annotations

import os
import pwd
from subprocess import CalledProcessError
from typing import TYPE_CHECKING

from hop3.core.events import InstallingDependencies, PreparingBuildEnv, emit
from hop3.lib import chdir, log

from ._base import LanguageToolchain

if TYPE_CHECKING:
    from hop3.core.env import Env
    from hop3.core.protocols import BuildArtifact


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

        # PHP needs no special runtime config - just workers
        return self._make_build_artifact(kind="php")

    def prepare_build_env(self, env: Env) -> None:
        """Prepare the environment for building the project, if necessary.

        This could involve setting up PHP-specific environment variables
        or toolchains.
        """
        emit(PreparingBuildEnv(self.app_name))
        log("Preparing PHP build environment...", level=2, fg="cyan")

    def install_dependencies(self, env: Env) -> None:
        """Install the PHP project's dependencies.

        If a custom build command is specified in hop3.toml [build] section,
        that command is run instead of the default composer install. This allows
        projects to run npm builds, use specific composer flags, etc.

        Otherwise, runs composer install if composer.json exists.
        """
        emit(InstallingDependencies(self.app_name))

        # Check if custom build command is specified in hop3.toml
        custom_build = self._get_custom_build_command()
        if custom_build:
            log(f"Running custom build command: {custom_build}", level=2, fg="cyan")
            self.shell(custom_build, env=self._get_env_dict(env))
            return

        if not self._has_composer():
            log(
                "No composer.json found - assuming vendored dependencies",
                level=2,
                fg="cyan",
            )
            return

        log("Installing PHP dependencies with composer...", level=2, fg="cyan")
        try:
            # Composer requires HOME to be set for cache directory
            self.shell(
                "composer install --no-interaction --optimize-autoloader",
                env=self._get_env_dict(env),
            )
            log("PHP dependencies installed successfully", level=2, fg="green")
        except CalledProcessError as e:
            msg = (
                f"Failed to install dependencies for PHP project '{self.app_name}': {e}"
            )
            raise RuntimeError(msg) from e

    def _get_env_dict(self, env: Env) -> dict[str, str]:
        """Get environment dict with required variables like HOME.

        Composer and npm require HOME to be set for their cache directories.
        In systemd services or restricted environments, HOME may not be set,
        so we fall back to pwd module or the hop3 user's home directory.
        """
        env_dict = dict(os.environ)
        env_dict.update(env)
        # Ensure HOME is set (required by composer and npm)
        if "HOME" not in env_dict or not env_dict["HOME"]:
            try:
                env_dict["HOME"] = pwd.getpwuid(os.getuid()).pw_dir
            except (KeyError, OSError):
                # Fallback to hop3 user's home directory
                env_dict["HOME"] = "/home/hop3"
        return env_dict
