# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Tests for create_virtual_environment() idempotency.

Regression: this function used to unconditionally wipe an existing venv,
which silently destroyed the install ``hop3-deploy --local`` had just
placed there in a separate step. It must now be a no-op when a working
venv already exists, unless ``force=True``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def fake_venv(tmp_path, monkeypatch):
    """Build a tmp venv that looks like a working one."""
    venv = tmp_path / "venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").write_text("#!/bin/sh\n")
    monkeypatch.setattr("hop3_installer.server_installer.python.VENV_DIR", venv)
    return venv


def test_existing_working_venv_is_preserved(fake_venv):
    """A working venv must not be wiped on default re-run."""
    from hop3_installer.server_installer import python as mod  # noqa: PLC0415

    rmtree = MagicMock()
    run_as_hop3 = MagicMock()
    with (
        patch.object(mod.shutil, "rmtree", rmtree),
        patch.object(mod, "run_as_hop3", run_as_hop3),
    ):
        mod.create_virtual_environment()

    rmtree.assert_not_called()
    run_as_hop3.assert_not_called()
    # Sanity check: the simulated python binary survived
    assert (fake_venv / "bin" / "python").exists()


def test_force_true_rebuilds_venv(fake_venv):
    """force=True must wipe and recreate even a working venv."""
    from hop3_installer.server_installer import python as mod  # noqa: PLC0415

    rmtree = MagicMock()
    run_as_hop3 = MagicMock()
    with (
        patch.object(mod.shutil, "rmtree", rmtree),
        patch.object(mod, "run_as_hop3", run_as_hop3),
        patch.object(mod, "_get_python_executable", return_value="/usr/bin/python3"),
    ):
        mod.create_virtual_environment(force=True)

    rmtree.assert_called_once_with(fake_venv)
    run_as_hop3.assert_called_once()
    assert "venv" in run_as_hop3.call_args.args[0]


def test_broken_venv_is_rebuilt(tmp_path, monkeypatch):
    """A directory at VENV_DIR without bin/python must be rebuilt."""
    venv = tmp_path / "venv"
    venv.mkdir()  # exists but no bin/python
    monkeypatch.setattr("hop3_installer.server_installer.python.VENV_DIR", venv)
    from hop3_installer.server_installer import python as mod  # noqa: PLC0415

    rmtree = MagicMock()
    run_as_hop3 = MagicMock()
    with (
        patch.object(mod.shutil, "rmtree", rmtree),
        patch.object(mod, "run_as_hop3", run_as_hop3),
        patch.object(mod, "_get_python_executable", return_value="/usr/bin/python3"),
    ):
        mod.create_virtual_environment()

    rmtree.assert_called_once_with(venv)
    run_as_hop3.assert_called_once()


def test_fresh_install_creates_venv(tmp_path, monkeypatch):
    """When VENV_DIR doesn't exist at all, just create it (no rmtree)."""
    venv = tmp_path / "does-not-exist"
    monkeypatch.setattr("hop3_installer.server_installer.python.VENV_DIR", venv)
    from hop3_installer.server_installer import python as mod  # noqa: PLC0415

    rmtree = MagicMock()
    run_as_hop3 = MagicMock()
    with (
        patch.object(mod.shutil, "rmtree", rmtree),
        patch.object(mod, "run_as_hop3", run_as_hop3),
        patch.object(mod, "_get_python_executable", return_value="/usr/bin/python3"),
    ):
        mod.create_virtual_environment()

    rmtree.assert_not_called()
    run_as_hop3.assert_called_once()
