# Copyright (c) 2023-2024, Abilian SAS

from pathlib import Path
from subprocess import CalledProcessError

from hop3.builders.base import Builder
from hop3.core.env import Env
from hop3.core.events import InstallingDependencies, PreparingBuildEnv, emit
from hop3.util import shell
from hop3.util.backports import chdir


class PHPBuilder(Builder):
    name = "PHP"
    requirements = ["composer"]

    def accept(self) -> bool:
        """
        Check if the application directory contains a composer.json file,
        indicating it is a PHP project.
        """
        return Path(self.app_path, "composer.json").exists()

    def build(self) -> None:
        """
        Build the PHP project by installing dependencies and potentially running custom scripts.
        """
        with chdir(self.app_path):
            env = self.get_env()
            self.prepare_build_env(env)
            self.install_dependencies()

    def prepare_build_env(self, env: Env) -> None:
        """
        Prepare the environment for building the project, if necessary.
        This could involve setting up PHP-specific environment variables or toolchains.
        """
        emit(PreparingBuildEnv(self.app_name))

        # Example: Configuring PHP environment or version (skipped here for brevity).
        # This step is optional and highly dependent on the project's requirements.

    def install_dependencies(self) -> None:
        """
        Install the PHP project's dependencies using composer.
        """
        emit(InstallingDependencies(self.app_name))

        try:
            shell("composer install", cwd=self.app_path)
        except CalledProcessError as e:
            raise RuntimeError(
                f"Failed to install dependencies for PHP project '{self.app_name}': {e}"
            )
