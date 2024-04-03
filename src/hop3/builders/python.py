# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

from pathlib import Path

from hop3.system.constants import ENV_ROOT
from hop3.util.backports import chdir
from hop3.util.console import log
from hop3.util.settings import parse_settings

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

    def get_env(self) -> dict:
        # Set unbuffered output and readable UTF-8 mapping
        env = {"PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "UTF_8:replace"}

        env_file = Path("ENV")
        if env_file.exists():
            env.update(parse_settings(env_file, env))
        return env

    def make_virtual_env(self, env) -> None:
        if not (self.virtual_env / "bin" / "activate").exists():
            self.create_virtualenv()

        activation_script = self.virtual_env / "bin" / "activate_this.py"
        exec(open(activation_script).read(), {"__file__": activation_script})

    def create_virtualenv(self) -> None:
        log(
            f"Creating or recreating virtualenv for '{self.app_name:s}'",
            level=5,
            fg="green",
        )
        self.shell(f"virtualenv --python=python3 {self.app_name:s}", cwd=ENV_ROOT)

    def install_virtualenv(self) -> None:
        log(f"Installing requirements for '{self.app_name}'", level=5, fg="green")

        pip = self.virtual_env / "bin" / "pip"
        if Path("requirements.txt").exists():
            self.shell(f"{pip} install -r requirements.txt")
        elif Path("pyproject.toml").exists():
            self.shell(f"{pip} install .")
        else:
            raise FileNotFoundError(
                f"requirements.txt or pyproject.toml not found for '{self.app_name}'"
            )
