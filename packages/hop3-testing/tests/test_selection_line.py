# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
A run says what chose its tests, before it starts and under its summary.

`hop3-test run --provider hetzner --with all --from local` rebuilt a server
for the full catalog run and ran the `smoke` profile, the default: nine
Procfile fixtures. It did so twice, and both summaries read "All 9 tests
passed", which is how a smoke run was recorded as the release's catalog run.
"""

from __future__ import annotations

from hop3_testing.cli.commands.test import describe_selection
from hop3_testing.cli.runners import _report_scope
from hop3_testing.util.console import PrintingConsole

_NONE: tuple[str, ...] = ()


def _line(mode: str = "smoke", **kwargs) -> str:
    args = {
        "app_names": _NONE,
        "statuses": _NONE,
        "covers": _NONE,
        "published": False,
        "published_statuses": _NONE,
        "selected": 9,
        "scanned": 243,
    } | kwargs
    return describe_selection(mode=mode, **args)


def test_the_default_profile_says_what_it_left_out_and_how_to_widen_it():
    assert _line() == (
        "profile smoke (tier fast; priority P0): 9 of 243 tests. "
        "`--mode full` runs every test; `--status` picks catalog tiers"
    )


def test_an_old_profile_name_is_shown_under_its_current_one():
    assert _line("dev").startswith("profile smoke ")


def test_the_full_profile_needs_no_hint():
    line = _line("full", selected=243)

    assert line.endswith(": 243 of 243 tests")
    assert "--mode full" not in line


def test_a_hand_picked_profile_says_so():
    assert "(a hand-picked list)" in _line("curated")


def test_a_status_selection_names_its_tiers_and_not_the_profile():
    line = _line(statuses=("golden", "beta"), selected=54)

    assert line == "catalog status golden, beta: 54 tests"


def test_named_apps_and_a_covers_tag_are_said():
    line = _line(app_names=("apps/test-apps-procfile",), covers=("nix",), selected=3)

    assert line == "the apps and paths named, covers nix: 3 tests"


def test_a_published_run_names_the_catalog():
    line = _line(published=True, published_statuses=("golden", "beta"))

    assert line == "the published catalog, status golden, beta"


def test_the_summary_repeats_the_selection(capsys):
    _report_scope(
        "profile smoke (tier fast; priority P0): 9 of 243 tests", [], PrintingConsole()
    )

    assert "Selection: profile smoke (tier fast; priority P0): 9 of 243 tests" in (
        capsys.readouterr().out
    )
