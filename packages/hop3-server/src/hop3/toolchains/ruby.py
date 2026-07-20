# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Language toolchain for Ruby projects."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from hop3.core.env import Env
from hop3.core.events import CreatingVirtualEnv, InstallingVirtualEnv, emit
from hop3.lib import chdir, log, prepend_to_path

from ._base import LanguageToolchain

if TYPE_CHECKING:
    from hop3.core.protocols import BuildArtifact


class RubyToolchain(LanguageToolchain):
    """Language toolchain for Ruby projects.

    This is responsible for setting up and building Ruby projects. It
    checks for the existence of a Gemfile to confirm it is a Ruby
    project, sets up a virtual environment, and installs dependencies
    using Bundler.
    """

    name = "Ruby"
    requirements = ["ruby", "gem", "bundle"]  # noqa: RUF012

    def accept(self) -> bool:
        return self.check_exists("Gemfile")

    def build(self) -> BuildArtifact:
        log(f"Building Ruby application '{self.app_name}'", level=1, fg="blue")

        with chdir(self.src_path):
            env = self.get_env()
            self.make_virtual_env(env)

            emit(InstallingVirtualEnv(self.app_name))
            log("Installing Ruby gems with bundler...", level=2, fg="cyan")
            # --frozen refuses to install when Gemfile.lock is missing or out of
            # sync with the Gemfile, instead of silently re-resolving and
            # producing a different gem set than the one that was tested.
            self.shell("bundle install --frozen", env=env)
            log("Ruby gems installed successfully", level=2, fg="green")

        # Compute environment variables for runtime
        # Include system gem path for access to system gems like bundler
        system_gem_path = os.environ.get(
            "GEM_PATH", "/usr/share/gems:/usr/local/share/gems"
        )
        env_vars = {
            "BUNDLE_PATH": str(self.virtual_env),
            "BUNDLE_USER_HOME": str(self.virtual_env / ".bundle"),
            "BUNDLE_USER_CACHE": str(self.virtual_env / ".bundle/cache"),
            "GEM_HOME": str(self.virtual_env),
            "GEM_PATH": f"{self.virtual_env}:{system_gem_path}",
        }

        # Paths to prepend to PATH
        path_prepend = [
            str(self.virtual_env / "bin"),
            str(self.src_path / ".bin"),
        ]

        # Create runtime configuration
        runtime = self._make_runtime_config(
            env_vars=env_vars,
            path_prepend=path_prepend,
        )

        # Return complete BuildArtifact with runtime config
        return self._make_build_artifact(
            kind="ruby",
            runtime=runtime,
        )

    def get_env(self) -> Env:
        path = prepend_to_path(
            [
                self.virtual_env / "bin",
                self.src_path / ".bin",
            ],
        )

        # Get system GEM_PATH to ensure system gems (like bundler) are available
        # This is critical on Fedora 42+ where bundler is installed as a system gem
        system_gem_path = os.environ.get(
            "GEM_PATH", "/usr/share/gems:/usr/local/share/gems"
        )

        # Start with system environment (needed for HOME, USER, LANG, etc.)
        # then override with our Ruby-specific settings
        env = Env(os.environ)
        env.update(
            {
                "VIRTUAL_ENV": str(self.virtual_env),
                "PATH": path,
                # Multiple bundler settings to ensure gems are installed locally
                # This prevents permission errors when running as hop3 user
                "BUNDLE_PATH": str(self.virtual_env),
                "BUNDLE_USER_HOME": str(self.virtual_env / ".bundle"),
                "BUNDLE_USER_CACHE": str(self.virtual_env / ".bundle/cache"),
                "GEM_HOME": str(self.virtual_env),
                # Prepend app gem path but keep system paths for bundler access
                "GEM_PATH": f"{self.virtual_env}:{system_gem_path}",
            },
        )
        env.parse_settings(self.env_file)
        return env

    def make_virtual_env(self, env: Env) -> None:
        """Create a virtual environment for the specified environment.

        Args:
        ----
            env (Env): The environment settings to use for creating the virtual environment.
        """
        if not self.virtual_env.exists():
            emit(CreatingVirtualEnv(self.app_name))
            self.virtual_env.mkdir(parents=True)

        # Always ensure bundle directories exist and are configured
        bundle_dir = self.virtual_env / ".bundle"
        bundle_cache = bundle_dir / "cache"
        bundle_cache.mkdir(parents=True, exist_ok=True)

        # Set bundle config in the app's source directory using modern syntax
        # The 'set' command works in both old and new bundler versions
        self.shell(f"bundle config set path {self.virtual_env}", env=env)
