# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Shared pytest fixtures for hop3-installer tests."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from hop3_installer.common import run_cmd
from hop3_installer.deployer.deploy import Deployer
from hop3_installer.server_installer import user

if TYPE_CHECKING:
    from collections.abc import Generator, MutableMapping
    from pathlib import Path


@pytest.fixture
def clean_env() -> Generator[MutableMapping[str, str]]:
    """
    Provide a clean environment without HOP3_* variables.

    Saves and restores original environment after test.
    """
    original = os.environ.copy()

    # Remove all HOP3_* variables
    hop3_vars = [k for k in os.environ if k.startswith("HOP3_")]
    for var in hop3_vars:
        del os.environ[var]

    yield os.environ

    # Restore original environment
    os.environ.clear()
    os.environ.update(original)


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for tests."""
    return tmp_path


@pytest.fixture
def mock_project_root(tmp_path: Path) -> Path:
    """Create a mock project root with expected structure."""
    root = tmp_path / "hop3"
    root.mkdir()

    # Create expected directories and files
    (root / "packages").mkdir()
    (root / "packages" / "hop3-server").mkdir()
    (root / "packages" / "hop3-cli").mkdir()
    (root / "pyproject.toml").write_text("[project]\nname = 'hop3'\n")
    (root / ".git").mkdir()

    return root


@pytest.fixture
def sample_os_release_debian(tmp_path: Path) -> Path:
    """Create a sample /etc/os-release for Debian."""
    content = """PRETTY_NAME="Ubuntu 24.04 LTS"
NAME="Ubuntu"
VERSION_ID="24.04"
VERSION="24.04 LTS (Noble Numbat)"
VERSION_CODENAME=noble
ID=ubuntu
ID_LIKE=debian
HOME_URL="https://www.ubuntu.com/"
"""
    os_release = tmp_path / "os-release"
    os_release.write_text(content)
    return os_release


@pytest.fixture
def sample_os_release_fedora(tmp_path: Path) -> Path:
    """Create a sample /etc/os-release for Fedora."""
    content = """NAME="Fedora Linux"
VERSION="40 (Workstation Edition)"
ID=fedora
VERSION_ID=40
VERSION_CODENAME=""
PLATFORM_ID="platform:f40"
"""
    os_release = tmp_path / "os-release"
    os_release.write_text(content)
    return os_release


@pytest.fixture
def hop3_shell_is_local(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Run the installer's as-hop3 shell scripts in a local shell.

    The scripts themselves run (``read_as_hop3``'s absence test, the
    ``cat > file && chmod``); only the ``su - hop3`` around them is gone,
    since the test host has no hop3 user.
    """

    def run(script, *, check=False, timeout=None, stdin_text=None):
        return run_cmd(
            ["sh", "-c", script], check=check, timeout=timeout, stdin_text=stdin_text
        )

    monkeypatch.setattr(user, "run_as_hop3_shell", run)


@pytest.fixture
def installer_runs_recorded(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """
    Record each run of the bundled installer instead of uploading it.

    The arguments are appended to the fake backend's ``commands`` too, when it
    keeps that list, so a test reads the order of everything the deployer did.
    """
    runs: list[str] = []

    def run_installer(self, args: str) -> bool:
        runs.append(args)
        commands = getattr(self.backend, "commands", None)
        if commands is not None:
            commands.append(f"install-server.py{args}")
        return True

    monkeypatch.setattr(Deployer, "_run_installer", run_installer)
    return runs
