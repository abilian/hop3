# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Builder for Python projects."""

from __future__ import annotations

from pathlib import Path

from hop3.core.env import Env
from hop3.core.events import CreatingVirtualEnv, InstallingVirtualEnv, emit
from hop3.core.protocols import BuildArtifact
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
        import shutil

        python_path = self.virtual_env / "bin" / "python"

        # Check if virtualenv exists
        if (self.virtual_env / "bin").exists():
            # Verify the Python binary is valid (not a broken symlink)
            if python_path.exists():
                # Check if it's actually executable
                try:
                    import subprocess

                    result = subprocess.run(
                        [str(python_path), "--version"],
                        check=False,
                        capture_output=True,
                        timeout=5,
                    )
                    if result.returncode == 0:
                        # Virtualenv is valid, nothing to do
                        return
                except (subprocess.SubprocessError, OSError):
                    pass

            # Virtualenv exists but is broken - remove it
            print(f"Removing broken virtualenv at {self.virtual_env} (broken symlinks)")
            shutil.rmtree(self.virtual_env, ignore_errors=True)

        emit(CreatingVirtualEnv(self.app_name))

        self.shell(f"virtualenv {self.virtual_env}")
        # TODO: consider using the built-in venv module instead of
        # (or as an alternative to) virtualenv

        # Verify the virtualenv was created successfully
        if not python_path.exists():
            msg = f"Virtual environment creation failed: {python_path} does not exist"
            raise RuntimeError(msg)

        # Verify it's executable
        try:
            import subprocess

            result = subprocess.run(
                [str(python_path), "--version"],
                check=False,
                capture_output=True,
                timeout=5,
            )
            if result.returncode != 0:
                msg = f"Virtual environment Python is not working: {python_path}"
                raise RuntimeError(msg)
        except (subprocess.SubprocessError, OSError) as e:
            msg = f"Virtual environment Python is not executable: {python_path}: {e}"
            raise RuntimeError(msg) from e

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
