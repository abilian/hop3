# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""User mode-overrides: built-ins overlaid by a TOML file, editable from the UI.

The overrides file ($HOP3_TEST_MODES) lets the Test Lab edit profiles without
touching code; load_modes() merges it over the built-in MODES so every
mode-resolution path (web trigger, scheduler, `hop3-test --mode X`) sees the
edit. Built-ins can be overridden or reset, but never deleted.
"""

from __future__ import annotations

import pytest
from hop3_testing.selector import (
    BUILTIN_MODE_NAMES,
    ModeConfig,
    delete_mode,
    get_mode_config,
    list_modes,
    load_modes,
    reset_mode,
    save_mode,
)
from hop3_testing.selector.modes import MODES


@pytest.fixture(autouse=True)
def _isolated_modes_file(tmp_path, monkeypatch):
    """Point the overrides file at a throwaway path for each test."""
    monkeypatch.setenv("HOP3_TEST_MODES", str(tmp_path / "test-modes.toml"))


def test_defaults_when_no_file():
    assert set(load_modes()) == set(MODES)
    assert get_mode_config("ci").tiers == MODES["ci"].tiers


def test_override_builtin_persists_and_resolves(tmp_path):
    edited = ModeConfig(
        name="ci",
        tiers=["fast"],  # dropped "medium"
        priorities=["P0"],
        targets=["docker"],
        description="CI, fast only",
        max_duration_minutes=10,
    )
    save_mode("ci", edited)

    assert (tmp_path / "test-modes.toml").is_file()
    assert get_mode_config("ci").tiers == ["fast"]
    assert load_modes()["ci"].description == "CI, fast only"
    # Other built-ins are untouched.
    assert get_mode_config("nightly").tiers == MODES["nightly"].tiers


def test_reset_builtin_reverts_to_default():
    save_mode(
        "ci",
        ModeConfig(name="ci", tiers=["fast"], priorities=["P0"], targets=["docker"]),
    )
    assert get_mode_config("ci").tiers == ["fast"]

    reset_mode("ci")

    assert get_mode_config("ci").tiers == MODES["ci"].tiers


def test_add_and_delete_custom_mode():
    save_mode(
        "myprofile",
        ModeConfig(
            name="myprofile",
            tiers=["fast"],
            priorities=["P0"],
            targets=["docker"],
            description="One-off custom profile",
        ),
    )
    assert "myprofile" in list_modes()
    assert get_mode_config("myprofile").description == "One-off custom profile"

    delete_mode("myprofile")

    assert "myprofile" not in list_modes()


def test_explicit_test_list_round_trips():
    """A curated profile's explicit `tests` list persists and reloads."""
    names = ["apps/test-apps-procfile/000-static", "demos/demo01"]
    save_mode(
        "mycurated",
        ModeConfig(
            name="mycurated",
            tiers=[],
            priorities=[],
            targets=["docker"],
            description="hand-picked",
            tests=names,
        ),
    )
    assert get_mode_config("mycurated").tests == names
    delete_mode("mycurated")


def test_builtin_cannot_be_deleted():
    with pytest.raises(ValueError, match="built-in"):
        delete_mode("ci")


def test_custom_cannot_be_reset():
    save_mode(
        "myprofile",
        ModeConfig(
            name="myprofile", tiers=["fast"], priorities=["P0"], targets=["docker"]
        ),
    )
    with pytest.raises(ValueError, match="not a built-in"):
        reset_mode("myprofile")


def test_malformed_file_falls_back_to_builtins(tmp_path):
    (tmp_path / "test-modes.toml").write_text(
        "this is = = not valid toml [[[", encoding="utf-8"
    )
    assert set(load_modes()) == set(MODES)


def test_builtin_mode_names_matches_seed():
    assert frozenset(MODES) == BUILTIN_MODE_NAMES
