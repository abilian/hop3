# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the state.toml reader/writer (ADR 042 Step 4)."""

from __future__ import annotations

import os
import stat
from typing import TYPE_CHECKING

import pytest
from hop3_cli.core.cli_state import (
    CliState,
    get_current_server,
    load_state,
    save_state,
    set_current_server,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def redirect_state_path(tmp_path, monkeypatch):
    """Point ``default_state_path`` at tmp_path so tests stay isolated."""
    state_toml = tmp_path / "state.toml"
    monkeypatch.setattr(
        "hop3_cli.core.cli_state.default_state_path",
        lambda: state_toml,
    )
    return state_toml


# ---- load_state ---------------------------------------------------------


def test_load_state_missing_file(redirect_state_path: Path) -> None:
    state = load_state()
    assert state.path == redirect_state_path
    assert state.current_server is None


def test_load_state_reads_current_server(redirect_state_path: Path) -> None:
    redirect_state_path.write_text('current_server = "dev"\n')
    state = load_state()
    assert state.current_server == "dev"


def test_load_state_handles_empty_value(redirect_state_path: Path) -> None:
    """An explicit empty string is treated as 'not set'."""
    redirect_state_path.write_text('current_server = "   "\n')
    assert load_state().current_server is None


def test_load_state_handles_unparseable_file(redirect_state_path: Path) -> None:
    """Broken TOML → empty state; don't crash."""
    redirect_state_path.write_text("not valid toml [[[")
    state = load_state()
    assert state.current_server is None


# ---- save_state / set_current_server ------------------------------------


def test_set_current_server_creates_file(redirect_state_path: Path) -> None:
    set_current_server("dev")
    assert redirect_state_path.is_file()
    assert get_current_server() == "dev"


def test_set_current_server_clears_pointer(redirect_state_path: Path) -> None:
    """Passing None removes the pointer."""
    set_current_server("dev")
    set_current_server(None)
    assert get_current_server() is None


def test_save_state_chmods_600(redirect_state_path: Path) -> None:
    save_state(CliState(path=redirect_state_path, current_server="dev"))
    mode = stat.S_IMODE(os.stat(redirect_state_path).st_mode)
    assert redirect_state_path.is_file()
    if mode != 0:  # tmpfs may reject chmod
        assert mode == 0o600


def test_save_state_round_trip(redirect_state_path: Path) -> None:
    save_state(CliState(path=redirect_state_path, current_server="prod"))
    reloaded = load_state()
    assert reloaded.current_server == "prod"


def test_set_current_server_preserves_unrelated_keys(
    redirect_state_path: Path,
) -> None:
    """A future field next to current_server isn't clobbered when the
    pointer is updated. Forward-compat sanity check.
    """
    redirect_state_path.write_text(
        'current_server = "dev"\nfuture_field = "preserved"\n'
    )
    set_current_server("prod")
    content = redirect_state_path.read_text()
    assert 'current_server = "prod"' in content
    assert 'future_field = "preserved"' in content
