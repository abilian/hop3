# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

from pathlib import Path

from hop3.core.env import Env
from hop3.core.events import CreatingVirtualEnv, InstallingVirtualEnv, emit
from hop3.system.constants import ENV_ROOT
from hop3.util.backports import chdir

from .base import Builder


class PythonBuilder(Builder):
    name = "Python"
    requirements = ["python3", "pip", "virtualenv"]

    def accept(self) -> bool:
        return (
            Path(self.app_path, "requirements.txt").exists()
            or Path(self.app_path, "pyproject.toml").exists()
        )

    def build(self) -> None:
        with chdir(self.app_path):
            env = self.get_env()
            self.make_virtual_env(env)
            self.install_virtualenv()

    def get_env(self) -> Env:
        # Set unbuffered output and readable UTF-8 mapping
        env = Env({"PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "UTF_8:replace"})
        env.parse_settings("ENV")
        return env

    def make_virtual_env(self, env) -> None:
        if not (self.virtual_env / "bin" / "activate").exists():
            self.create_virtualenv()

        activation_script = self.virtual_env / "bin" / "activate_this.py"
        exec(activation_script.read_text(), {"__file__": activation_script})

    def create_virtualenv(self) -> None:
        emit(CreatingVirtualEnv(self.app_name))

        self.shell(f"virtualenv --python=python3 {self.app_name:s}", cwd=ENV_ROOT)

    def install_virtualenv(self) -> None:
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
