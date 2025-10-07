# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Builder for Python projects."""

from __future__ import annotations

from pathlib import Path

from hop3.core.env import Env
from hop3.core.events import CreatingVirtualEnv, InstallingVirtualEnv, emit
from hop3.lib import chdir

from ._base import Builder


class PythonBuilder(Builder):
    """Builder for Python projects.

    This provides the necessary methods to build Python projects by
    creating a virtual environment and installing dependencies. It
    checks for specific files to ascertain the presence of a Python
    project and handles environment setup.
    """

    name = "Python"
    requirements = ["python3", "pip", "virtualenv"]  # noqa: RUF012

    def accept(self) -> bool:
        return self.check_exists(["requirements.txt", "pyproject.toml"])

    def build(self) -> None:
        # Change the directory to the source path and proceed with building the project
        with chdir(self.src_path):
            self.make_virtual_env()
            self.install_virtualenv()

    def get_env(self) -> Env:
        # Create an environment with specific settings for Python execution
        env = Env({"PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "UTF_8:replace"})
        env.parse_settings(Path("ENV"))
        return env

    def make_virtual_env(self) -> None:
        """Create and activate a virtual environment."""

        if (self.virtual_env / "bin").exists():
            return

        emit(CreatingVirtualEnv(self.app_name))

        # Use Python's built-in venv module (available since Python 3.3)
        # This is more portable than virtualenv which requires separate installation
        try:
            self.shell(f"python3 -m venv {self.virtual_env}")
        except Exception as e:
            error_msg = (
                f"Failed to create virtual environment for '{self.app_name}': {e}\n\n"
                "This usually means the python3-venv package is not installed.\n"
                "On Debian/Ubuntu systems, install it with:\n"
                "  sudo apt-get install python3-venv\n\n"
                "On RHEL/CentOS/Fedora systems, install it with:\n"
                "  sudo dnf install python3-virtualenv\n"
            )
            raise RuntimeError(error_msg) from e

    def install_virtualenv(self) -> None:
        """Install virtual environment and necessary dependencies for the
        application."""
        emit(InstallingVirtualEnv(self.app_name))

        python = self.virtual_env / "bin" / "python"

        # Install dependencies from requirements.txt if it exists
        if Path("requirements.txt").exists():
            self.shell(f"{python} -m pip install -r requirements.txt")
        # Install dependencies using pyproject.toml if it exists
        elif Path("pyproject.toml").exists():
            self.shell(f"{python} -m pip install .")
        else:
            # This should never happen as `accept` checks for the presence of
            # requirements.txt or pyproject.toml
            msg = f"requirements.txt or pyproject.toml not found for '{self.app_name}'"
            raise FileNotFoundError(msg)
