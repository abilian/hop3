# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from pathlib import Path

from hop3.core.env import Env
from hop3.core.events import CreatingVirtualEnv, InstallingVirtualEnv, emit
from hop3.system.constants import ENV_ROOT
from hop3.util.backports import chdir

from .base import Builder


class PythonBuilder(Builder):
    """Build Python projects.

    Attributes
    ----------
        name (str): The name of the builder.
        requirements (list): The list of required dependencies for building a Python app.

    """

    name = "Python"
    requirements = ["python3", "pip", "virtualenv"]

    def accept(self) -> bool:
        """Check if either requirements.txt or pyproject.toml exists in the
        specified app_path.

        Returns
        -------
            bool: True if either requirements.txt or pyproject.toml exists in the specified app_path, otherwise False.

        """
        return (
            Path(self.app_path, "requirements.txt").exists()
            or Path(self.app_path, "pyproject.toml").exists()
        )

    def build(self) -> None:
        """Build the virtual environment for the application.

        This function sets up a virtual environment for the application using the specified app path.
        """
        with chdir(self.app_path):
            env = self.get_env()
            self.make_virtual_env(env)
            self.install_virtualenv()

    def get_env(self) -> Env:
        # Set unbuffered output and readable UTF-8 mapping
        """Get the environment settings.

        Returns
        -------
            Env: An instance of the Env class with the specified environment settings.

        """
        env = Env({"PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "UTF_8:replace"})
        env.parse_settings("ENV")
        return env

    def make_virtual_env(self, env) -> None:
        """Create a virtual environment for the provided environment.

        Args:
        ----
            env: The environment to create a virtual environment for.

        """
        if not (self.virtual_env / "bin" / "activate").exists():
            self.create_virtualenv()

        activation_script = self.virtual_env / "bin" / "activate_this.py"
        exec(activation_script.read_text(), {"__file__": activation_script})

    def create_virtualenv(self) -> None:
        """Create a virtual environment for the application.

        This method creates a virtual environment using Python 3 for the specified application name.
        """
        emit(CreatingVirtualEnv(self.app_name))

        self.shell(f"virtualenv --python=python3 {self.app_name:s}", cwd=ENV_ROOT)

    def install_virtualenv(self) -> None:
        """Install virtual environment and necessary dependencies for the
        application.

        Raises
        ------
            FileNotFoundError: If requirements.txt or pyproject.toml is not found for the application.

        """
        emit(InstallingVirtualEnv(self.app_name))

        pip = self.virtual_env / "bin" / "pip"
        if Path("requirements.txt").exists():
            self.shell(f"{pip} install -r requirements.txt")
        elif Path("pyproject.toml").exists():
            self.shell(f"{pip} install .")
        else:
            raise FileNotFoundError(
                f"requirements.txt or pyproject.toml not found for '{self.app_name}'",
            )
