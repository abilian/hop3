# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from subprocess import CalledProcessError
from typing import TYPE_CHECKING

from hop3.core.events import InstallingDependencies, PreparingBuildEnv, emit
from hop3.util import chdir, shell

from ._base import Builder

if TYPE_CHECKING:
    from hop3.core.env import Env


class PHPBuilder(Builder):
    """Build PHP projects.

    Attributes
    ----------
        name (str): The name of the builder, in this case 'PHP'.
        requirements (list): A list of requirements, in this case ['composer'].

    """

    name = "PHP"
    requirements = ["composer"]  # noqa: RUF012

    def accept(self) -> bool:
        """Check if the application directory contains a composer.json file,
        indicating it is a PHP project.
        """
        return self.check_exists("composer.json")

    def build(self) -> None:
        """Build the PHP project by installing dependencies and potentially
        running custom scripts.
        """
        with chdir(self.app_path):
            env = self.get_env()
            self.prepare_build_env(env)
            self.install_dependencies()

    def prepare_build_env(self, env: Env) -> None:
        """Prepare the environment for building the project, if necessary.

        This could involve setting up PHP-specific environment variables
        or toolchains.
        """
        emit(PreparingBuildEnv(self.app_name))

        # Example: Configuring PHP environment or version (skipped here for brevity).
        # This step is optional and highly dependent on the project's requirements.

    def install_dependencies(self) -> None:
        """Install the PHP project's dependencies using composer."""
        emit(InstallingDependencies(self.app_name))

        try:
            shell("composer install", cwd=self.app_path)
        except CalledProcessError as e:
            msg = (
                f"Failed to install dependencies for PHP project '{self.app_name}': {e}"
            )
            raise RuntimeError(msg)
