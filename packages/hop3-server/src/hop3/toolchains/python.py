# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Language toolchain for Python projects."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from hop3.core.env import Env
from hop3.core.events import CreatingVirtualEnv, InstallingVirtualEnv, emit
from hop3.lib import chdir, log

from ._base import LanguageToolchain

# Lines that are options or includes rather than requirements themselves.
_NON_REQUIREMENT_PREFIXES = ("#", "-r ", "-c ", "-e ", "-f ", "--")


def _requirement_lines(text: str) -> list[str]:
    """
    The requirement entries of a requirements file, one per line.

    Continuations are joined first, so ``pkg==1.0 \\`` followed by ``--hash=...``
    is treated as the single requirement it is.
    """
    joined = text.replace("\\\n", " ")
    return [
        line
        for raw in joined.splitlines()
        if (line := raw.strip()) and not line.startswith(_NON_REQUIREMENT_PREFIXES)
    ]


def unpinned_requirements(text: str) -> list[str]:
    """
    Requirements that do not pin an exact version.

    A dependency without ``==`` (or an accompanying hash) resolves to whatever
    satisfies it on the day of the build, so two deploys of the same commit can
    install different code.
    """
    return [
        req
        for req in _requirement_lines(text)
        if "==" not in req and "--hash=" not in req
    ]


def requirements_are_hashed(text: str) -> bool:
    """
    True when every requirement carries a hash, enabling ``--require-hashes``.

    Version pinning fixes *which release* is installed; a hash additionally
    fixes *which bytes*, so a tampered or re-uploaded artefact is rejected.
    """
    reqs = _requirement_lines(text)
    return bool(reqs) and all("--hash=" in req for req in reqs)


def _find_best_python() -> str:
    """
    Find the best available Python interpreter (3.12, 3.11, 3.10, or fallback).

    On RHEL 9 clones, /usr/bin/python3 is Python 3.9 which is too old.
    We prefer Python 3.12 > 3.11 > 3.10 > python3.

    Returns:
        Path to the best Python interpreter.
    """
    candidates = [
        "/usr/bin/python3.12",
        "/usr/bin/python3.11",
        "/usr/bin/python3.10",
        "/usr/bin/python3",
    ]
    for python in candidates:
        if Path(python).exists():
            # Verify it actually works
            try:
                result = subprocess.run(
                    [python, "--version"],
                    check=False,
                    capture_output=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    log(
                        f"Using Python: {python} ({result.stdout.decode().strip()})",
                        level=2,
                        fg="green",
                    )
                    return python
            except (subprocess.SubprocessError, OSError):
                continue
    # Last resort fallback
    return "/usr/bin/python3"


if TYPE_CHECKING:
    from hop3.core.protocols import BuildArtifact


class PythonToolchain(LanguageToolchain):
    """
    Language toolchain for Python projects.

    This provides the necessary methods to build Python projects by
    creating a virtual environment and installing dependencies. It
    checks for specific files to ascertain the presence of a Python
    project and handles environment setup.
    """

    name = "Python"
    requirements = ["python3", "pip"]  # ruff:ignore[mutable-class-default]

    def accept(self) -> bool:
        return self.check_exists(["requirements.txt", "pyproject.toml"])

    def build(self) -> BuildArtifact:
        """
        Build the Python application by creating a virtualenv and installing dependencies.

        Returns:
            BuildArtifact containing the virtualenv location and runtime configuration
        """
        # Change the directory to the source path and proceed with building the project
        with chdir(self.src_path):
            self.make_virtual_env()
            self.install_virtualenv()

        # Compute environment variables for runtime
        env_vars = {
            "PYTHONUNBUFFERED": "1",
            "PYTHONIOENCODING": "UTF_8:replace",
        }

        # Add src/ to PYTHONPATH for src-layout projects
        src_dir = self.src_path / "src"
        if src_dir.is_dir():
            env_vars["PYTHONPATH"] = str(src_dir)

        # Paths to prepend to PATH
        venv_bin = self.virtual_env / "bin"
        path_prepend = [str(venv_bin)] if venv_bin.exists() else []

        # Create runtime configuration
        runtime = self._make_runtime_config(
            env_vars=env_vars,
            path_prepend=path_prepend,
        )

        # Return complete BuildArtifact with runtime config
        return self._make_build_artifact(
            kind="python",
            runtime=runtime,
            metadata={
                "python_path": str(self.virtual_env / "bin" / "python"),
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
        # Use the best available Python with the built-in venv module.
        # On RHEL 9 clones, /usr/bin/python3 is Python 3.9, but Python 3.12 is installed.
        # venv is part of Python's standard library (3.3+), no external package needed.
        python = _find_best_python()
        self.shell(f"{python} -m venv {self.virtual_env}")

        # Verify the virtualenv was created successfully
        if not python_path.exists():
            msg = f"Virtual environment creation failed: {python_path} does not exist"
            raise RuntimeError(msg)

        if not self._is_python_executable(python_path):
            msg = f"Virtual environment Python is not working: {python_path}"
            raise RuntimeError(msg)

        # Upgrade pip and install setuptools
        # - pip upgrade ensures proper PEP 517 build support
        # - setuptools is needed because Python 3.12+ doesn't include it by default,
        #   but many packages (e.g., older gunicorn) still depend on pkg_resources
        self.shell(f"{python_path} -m pip install --upgrade pip setuptools")

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
        """
        Install virtual environment and necessary dependencies for the
        application.
        """
        emit(InstallingVirtualEnv(self.app_name))

        python = self.virtual_env / "bin" / "python"

        assert self.src_path.exists()
        assert self.virtual_env.exists()
        assert python.exists()

        # Check for uv.lock first - if present, use uv for exact locked versions
        uv_lock_file = self.src_path / "uv.lock"
        if uv_lock_file.exists():
            if self._ensure_uv_installed():
                self._install_with_uv()
                return
            log(
                "uv.lock found but uv installation failed, falling back to pip",
                level=2,
                fg="yellow",
            )

        # Ensure pip and setuptools are up to date before installing dependencies
        # This is essential for existing virtualenvs that may lack setuptools
        # (Python 3.12+ doesn't include setuptools by default, but many packages
        # like older gunicorn versions still depend on pkg_resources)
        self.shell(f"{python} -m pip install --upgrade pip setuptools")

        # Install dependencies from requirements.txt if it exists
        # Use absolute paths based on self.src_path to avoid directory confusion
        requirements_file = self.src_path / "requirements.txt"
        pyproject_file = self.src_path / "pyproject.toml"

        # DEBUG: List all files in src_path to diagnose the issue
        files_in_src = sorted(f.name for f in self.src_path.iterdir())
        log(f"Files in {self.src_path}: {files_in_src}", level=3, fg="yellow")

        # Per ADR 039:
        # - Both files present → error (silent override is a design smell).
        # - Drop `--upgrade` from pip invocations: the packager's intent
        #   (pinned / unpinned) is honoured; deploys are reproducible
        #   when a frozen requirements.txt is committed.
        match requirements_file.exists(), pyproject_file.exists():
            case True, True:
                msg = (
                    f"Both `requirements.txt` and `pyproject.toml` exist for "
                    f"'{self.app_name}'. Declare one explicitly via "
                    f"`[build.python].strategy` in hop3.toml, or remove the "
                    f"one you don't want to drive the install."
                )
                raise RuntimeError(msg)
            case True, False:
                text = requirements_file.read_text()
                unpinned = unpinned_requirements(text)
                if unpinned:
                    shown = ", ".join(unpinned[:5])
                    msg = (
                        f"'{self.app_name}' has unpinned requirements ({shown}), so "
                        f"the build resolves to whatever satisfies them today and "
                        f"cannot be reproduced. Pin every dependency — "
                        f"`uv export --format requirements-txt` or "
                        f"`pip-compile --generate-hashes` — and commit the result."
                    )
                    raise RuntimeError(msg)
                # Hashes let pip verify each artefact, not merely its version.
                flags = " --require-hashes" if requirements_are_hashed(text) else ""
                log("Installing from requirements.txt", level=2, fg="green")
                self.shell(f"{python} -m pip install{flags} -r {requirements_file}")
            case False, True:
                log("Installing from pyproject.toml", level=2, fg="green")
                self.shell(f"{python} -m pip install .")
            case False, False:
                # This should never happen as `accept` checks for the presence of
                # requirements.txt or pyproject.toml
                msg = f"requirements.txt or pyproject.toml not found for '{self.app_name}'"
                raise FileNotFoundError(msg)

    def _has_uv(self) -> bool:
        """Check if uv is available on the system."""
        return shutil.which("uv") is not None

    def _ensure_uv_installed(self) -> bool:
        """
        Ensure uv is installed, installing it if necessary.

        Returns:
            True if uv is available (was already installed or installation succeeded)
            False if installation failed
        """
        if self._has_uv():
            return True

        log("Installing uv package manager...", level=2, fg="yellow")
        try:
            # Install uv using the official installer
            result = subprocess.run(
                ["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                log(f"Failed to install uv: {result.stderr}", level=1, fg="red")
                return False

            # Verify installation - uv installs to ~/.local/bin by default
            # We need to check common locations
            uv_paths = [
                Path.home() / ".local" / "bin" / "uv",
                Path("/usr/local/bin/uv"),
                Path.home() / ".cargo" / "bin" / "uv",
            ]
            for uv_path in uv_paths:
                if uv_path.exists():
                    log(f"uv installed successfully at {uv_path}", level=2, fg="green")
                    return True

            # Check if it's now in PATH
            if self._has_uv():
                log("uv installed successfully", level=2, fg="green")
                return True

            log("uv installation completed but binary not found", level=1, fg="red")
            return False
        except Exception as e:
            log(f"Error installing uv: {e}", level=1, fg="red")
            return False

    def _find_uv_binary(self) -> str:
        """Find the uv binary, checking common installation locations."""
        # Check PATH first
        uv_in_path = shutil.which("uv")
        if uv_in_path:
            return uv_in_path

        # Check common installation locations
        candidates = [
            Path.home() / ".local" / "bin" / "uv",
            Path.home() / ".cargo" / "bin" / "uv",
            Path("/usr/local/bin/uv"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)

        # Fallback - assume it's in PATH
        return "uv"

    def _install_with_uv(self) -> None:
        """Install dependencies using uv sync for exact locked versions."""
        uv_bin = self._find_uv_binary()
        log(f"Installing from uv.lock using {uv_bin} sync", level=2, fg="green")
        # uv sync installs exact versions from uv.lock into the virtualenv.
        #   --frozen: use lockfile exactly, don't update it
        #   --reinstall: force reinstall to guarantee the locked versions
        #   --no-dev: production deploy, dev-deps belong on the packager's
        #             machine not the runtime venv (ADR 039 Phase 1)
        # UV_PROJECT_ENVIRONMENT tells uv to use our existing virtualenv.
        env = os.environ.copy()
        env["UV_PROJECT_ENVIRONMENT"] = str(self.virtual_env)
        result = subprocess.run(
            [uv_bin, "sync", "--frozen", "--reinstall", "--no-dev"],
            cwd=self.src_path,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            log(f"uv sync failed: {result.stderr}", level=1, fg="red")
            raise subprocess.CalledProcessError(result.returncode, "uv sync")
        if result.stdout:
            log(result.stdout.strip(), level=2)
