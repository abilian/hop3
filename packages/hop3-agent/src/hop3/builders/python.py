# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Builder for Python projects."""

from __future__ import annotations

from pathlib import Path

from hop3.core.env import Env
from hop3.core.events import CreatingVirtualEnv, InstallingVirtualEnv, emit
from hop3.util import chdir

from ._base import Builder


class PythonBuilder(Builder):
    """Build Python projects."""

    name = "Python"
    requirements = ["python3", "pip", "virtualenv"]  # noqa: RUF012

    def accept(self) -> bool:
        return self.check_exists(["requirements.txt", "pyproject.toml"])

    def build(self) -> None:
        with chdir(self.src_path):
            self.make_virtual_env()
            self.install_virtualenv()

    def get_env(self) -> Env:
        env = Env({"PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "UTF_8:replace"})
        env.parse_settings(Path("ENV"))
        return env

    def make_virtual_env(self) -> None:
        """Create and activate a virtual environment."""
        if not (self.virtual_env / "bin" / "activate").exists():
            emit(CreatingVirtualEnv(self.app_name))
            self.shell(f"virtualenv --python=python3 {self.virtual_env}")

        activation_script = self.virtual_env / "bin" / "activate_this.py"
        exec(activation_script.read_text(), {"__file__": activation_script})

    def install_virtualenv(self) -> None:
        """Install virtual environment and necessary dependencies for the
        application.
        """
        emit(InstallingVirtualEnv(self.app_name))

        pip = self.virtual_env / "bin" / "pip"
        if Path("requirements.txt").exists():
            self.shell(f"{pip} install -r requirements.txt")
        elif Path("pyproject.toml").exists():
            self.shell(f"{pip} install .")
        else:
            msg = f"requirements.txt or pyproject.toml not found for '{self.app_name}'"
            raise FileNotFoundError(msg)
