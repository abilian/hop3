# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Language toolchain for Python projects."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from hop3.core.env import Env
from hop3.core.events import CreatingVirtualEnv, InstallingVirtualEnv, emit
from hop3.core.protocols import BuildArtifact
from hop3.lib import chdir, log

from ._base import LanguageToolchain


class PythonToolchain(LanguageToolchain):
    """Language toolchain for Python projects.

    This provides the necessary methods to build Python projects by
    creating a virtual environment and installing dependencies. It
    checks for specific files to ascertain the presence of a Python
    project and handles environment setup.
    """

    name = "Python"
    requirements = ["python3", "pip"]  # noqa: RUF012

    def accept(self) -> bool:
        return self.check_exists(["requirements.txt", "pyproject.toml"])

    def build(self) -> BuildArtifact:
        """Build the Python application by creating a virtualenv and installing dependencies.

        Returns:
            BuildArtifact containing the virtualenv location
        """
        # Change the directory to the source path and proceed with building the project
        with chdir(self.src_path):
            self.make_virtual_env()
            self.install_virtualenv()

        # Return a BuildArtifact describing what we built
        return BuildArtifact(
            kind="virtualenv",
            location=str(self.virtual_env),
            metadata={
                "python_path": str(self.virtual_env / "bin" / "python"),
                "app_name": self.app_name,
            },
        )

    def get_env(self) -> Env:
        # Create an environment with specific settings for Python execution
        env = Env({"PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "UTF_8:replace"})
        env.parse_settings(Path("ENV"))
        return env

    def make_virtual_env(self) -> None:
        """Create and activate a virtual environment."""
        python_path = self.virtual_env / "bin" / "python"

        # Check if virtualenv exists and is valid
        if (self.virtual_env / "bin").exists():
            if self._is_python_executable(python_path):
                return  # Virtualenv is valid, nothing to do

            # Virtualenv exists but is broken - remove it
            log(
                f"Removing broken virtualenv at {self.virtual_env}",
                level=2,
                fg="yellow",
            )
            shutil.rmtree(self.virtual_env, ignore_errors=True)

        emit(CreatingVirtualEnv(self.app_name))
        # Use /usr/bin/python3 with the built-in venv module.
        # venv is part of Python's standard library (3.3+), no external package needed.
        # This works on all platforms (Linux, macOS) without additional dependencies.
        self.shell(f"/usr/bin/python3 -m venv {self.virtual_env}")

        # Verify the virtualenv was created successfully
        if not python_path.exists():
            msg = f"Virtual environment creation failed: {python_path} does not exist"
            raise RuntimeError(msg)

        if not self._is_python_executable(python_path):
            msg = f"Virtual environment Python is not working: {python_path}"
            raise RuntimeError(msg)

        # Upgrade pip to ensure proper PEP 517 build support
        # This is necessary for Poetry and other modern build backends
        self.shell(f"{python_path} -m pip install --upgrade pip")

    def _is_python_executable(self, python_path: Path) -> bool:
        """Check if Python binary at path is valid and executable."""
        if not python_path.exists():
            return False
        try:
            result = subprocess.run(
                [str(python_path), "--version"],
                check=False,
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, OSError):
            return False

    def install_virtualenv(self) -> None:
        """Install virtual environment and necessary dependencies for the
        application."""
        emit(InstallingVirtualEnv(self.app_name))

        python = self.virtual_env / "bin" / "python"

        assert self.src_path.exists()
        assert self.virtual_env.exists()
        assert python.exists()

        # Install dependencies from requirements.txt if it exists
        # Use absolute paths based on self.src_path to avoid directory confusion
        requirements_file = self.src_path / "requirements.txt"
        pyproject_file = self.src_path / "pyproject.toml"

        # DEBUG: List all files in src_path to diagnose the issue
        files_in_src = sorted(f.name for f in self.src_path.iterdir())
        log(f"Files in {self.src_path}: {files_in_src}", level=3, fg="yellow")

        # Always use requirements.txt if it exists, even if pyproject.toml also exists
        # This prevents pip from using a stray/unwanted pyproject.toml
        match requirements_file.exists(), pyproject_file.exists():
            case True, _:
                log("Installing from requirements.txt", level=2, fg="green")
                self.shell(f"{python} -m pip install -r {requirements_file}")
            case False, True:
                log("Installing from pyproject.toml", level=2, fg="green")
                self.shell(f"{python} -m pip install .")
            case False, False:
                # This should never happen as `accept` checks for the presence of
                # requirements.txt or pyproject.toml
                msg = f"requirements.txt or pyproject.toml not found for '{self.app_name}'"
                raise FileNotFoundError(msg)
