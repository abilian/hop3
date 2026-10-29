# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Language toolchain for Python projects."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

from hop3.core.artifacts import WEB_WORKER_KINDS
from hop3.core.env import Env
from hop3.core.events import CreatingVirtualEnv, InstallingVirtualEnv, emit
from hop3.lib import Diagnosis, abort_with_diagnosis, chdir, log

from ._base import LanguageToolchain

# Lines that are options or includes rather than requirements themselves.
_NON_REQUIREMENT_PREFIXES = ("#", "-r ", "-c ", "-e ", "-f ", "--")

#: Seconds the uv installer (a download plus a shell script) may take.
_UV_INSTALL_TIMEOUT = 300


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
            if not self._run_declared_build(env=self._venv_env()):
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
        wsgi = self._discover_wsgi_module(runtime.workers)
        if wsgi:
            runtime.workers["wsgi"] = wsgi

        # Return complete BuildArtifact with runtime config
        return self._make_build_artifact(
            kind="python",
            runtime=runtime,
            metadata={
                "python_path": str(self.virtual_env / "bin" / "python"),
            },
        )

    def _discover_wsgi_module(self, workers: dict[str, str]) -> str | None:
        """
        The WSGI module to serve when the app declares no web-facing worker.

        Probes the conventional entry points (``wsgi.py``, ``app.py``, then a
        Django ``<project>/wsgi.py``). Returns None when a web worker is already
        declared (Procfile or hop3.toml) or nothing conventional is found.
        """
        declared = set(workers)
        if self.context is not None:
            declared |= set(
                self.context.app_config.get("procfile", {}).get("workers", {})
            )
        if declared & WEB_WORKER_KINDS:
            return None

        probes = [("wsgi.py", "wsgi:application"), ("app.py", "app:app")]
        django = next(
            (
                child
                for child in sorted(self.src_path.iterdir())
                if child.is_dir() and (child / "wsgi.py").exists()
            ),
            None,
        )
        if django is not None:
            probes.append((f"{django.name}/wsgi.py", f"{django.name}.wsgi:application"))

        for file_check, module in probes:
            if (self.src_path / file_check).exists():
                log(
                    f"  Auto-detected WSGI module: {module} (from {file_check})",
                    level=1,
                    fg="green",
                )
                return module
        return None

    def get_env(self) -> Env:
        # Create an environment with specific settings for Python execution
        env = Env({"PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "UTF_8:replace"})
        env.parse_settings(Path("ENV"))
        return env

    def _venv_env(self) -> dict[str, str]:
        """
        An environment in which bare ``python``/``pip`` mean the app's venv.

        A recipe's ``[build].build = "pip install -r requirements.txt"`` means
        *the application's* pip, which is the only reading that makes sense: the
        command exists to populate the venv the toolchain just created. Run with
        the ambient environment instead, bare ``pip`` is the system interpreter's
        — and on a distribution that marks its Python externally managed (PEP 668,
        Debian/Ubuntu), pip then refuses outright and the build dies with advice
        to create a virtualenv, which is exactly what Hop3 already did.

        This is why the toolchain's own install path spells every call
        ``{venv}/bin/python -m pip``. A declared command cannot be rewritten that
        way, so it gets the PATH instead.
        """
        env = dict(os.environ)
        venv_bin = self.virtual_env / "bin"
        env["VIRTUAL_ENV"] = str(self.virtual_env)
        env["PATH"] = f"{venv_bin}{os.pathsep}{env.get('PATH', '')}"
        # A stale PYTHONHOME points the venv interpreter at another installation.
        env.pop("PYTHONHOME", None)
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

        for required in (self.src_path, self.virtual_env, python):
            if not required.exists():
                abort_with_diagnosis(
                    Diagnosis(
                        component="Python toolchain",
                        action="install dependencies",
                        reason=f"{required} does not exist",
                        hint=(
                            "The virtualenv step did not leave a working venv; "
                            "check the build log above for the venv creation error"
                        ),
                    )
                )

        # A uv.lock pins the exact dependency tree, so only uv may install it:
        # pip would ignore the lockfile and resolve something else.
        if (self.src_path / "uv.lock").exists():
            self._ensure_uv_installed()
            self._install_with_uv()
            return

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

    def _ensure_uv_installed(self) -> None:
        """
        Make uv available, installing it if necessary; abort if that fails.

        The caller has a uv.lock, which only uv can honour, so there is no
        fallback: a build that silently ignored the lockfile would ship a
        dependency tree nobody locked.
        """
        if self._locate_uv():
            return

        log("Installing uv package manager...", level=2, fg="yellow")
        command = "curl -LsSf https://astral.sh/uv/install.sh | sh"
        try:
            result = subprocess.run(
                ["sh", "-c", command],
                check=False,
                capture_output=True,
                text=True,
                timeout=_UV_INSTALL_TIMEOUT,
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            self._abort_uv_unavailable(f"`{command}` failed: {e}")

        if result.returncode != 0:
            output = (result.stderr or result.stdout or "").strip()
            self._abort_uv_unavailable(
                f"`{command}` exited with status {result.returncode}: {output[-1500:]}"
            )

        uv_bin = self._locate_uv()
        if uv_bin is None:
            searched = ", ".join(str(p) for p in self._uv_candidates())
            self._abort_uv_unavailable(
                f"the uv installer succeeded but no uv binary is on PATH or at {searched}"
            )
        log(f"uv installed successfully at {uv_bin}", level=2, fg="green")

    def _abort_uv_unavailable(self, reason: str) -> NoReturn:
        abort_with_diagnosis(
            Diagnosis(
                component="Python toolchain",
                action="install dependencies from uv.lock",
                reason=f"uv is not available for '{self.app_name}': {reason}",
                hint=(
                    "Make uv available to the hop3 user (on PATH or in "
                    "~/.local/bin), or remove uv.lock to install from "
                    "requirements.txt / pyproject.toml with pip"
                ),
            )
        )

    def _uv_candidates(self) -> list[Path]:
        """
        Where uv is commonly installed, in preference order.

        Its own method so a test can control it: reading the real filesystem
        made `_find_uv_binary`'s fallback depend on whether the developer's
        machine happens to have uv in one of these places.
        """
        return [
            Path.home() / ".local" / "bin" / "uv",
            Path.home() / ".cargo" / "bin" / "uv",
            Path("/usr/local/bin/uv"),
        ]

    def _locate_uv(self) -> str | None:
        """The uv binary on PATH, else in a common install location, else None."""
        uv_in_path = shutil.which("uv")
        if uv_in_path:
            return uv_in_path
        return next((str(p) for p in self._uv_candidates() if p.exists()), None)

    def _find_uv_binary(self) -> str:
        """Find the uv binary, falling back to the bare name for PATH lookup."""
        return self._locate_uv() or "uv"

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
