# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
apps/bad opt-out + DEFERRED.md business-drop skip (audit C6).

An explicit `expects-failure = false` must win over the apps/bad path default,
and a DEFERRED.md business-drop (an app dropped for business reasons that still
deploys fine) must be skipped from the run — not reported as a failing negative
test.
"""

from __future__ import annotations

from pathlib import Path

from hop3_testing.catalog.loader import (
    _parse_test_definition,
    generate_test_definition_from_hop3_toml,
)
from hop3_testing.catalog.scanner import Catalog

# ---- loader: explicit `expects-failure = false` opts back out ----


def test_hop3_toml_bad_app_explicit_false_opts_out():
    td = generate_test_definition_from_hop3_toml(
        Path("apps/bad/real-apps-docker-bad/x"),
        {"metadata": {"id": "x"}, "test": {"expects-failure": False}},
    )
    assert td.expects_failure is False  # before the fix this returned True


def test_standalone_test_toml_bad_dir_explicit_false_opts_out():
    td = _parse_test_definition(
        {
            "test": {
                "name": "n",
                "tier": "fast",
                "priority": "P0",
                "expects-failure": False,
            }
        },
        Path("apps/bad/foo/test.toml"),
    )
    assert td.expects_failure is False


def test_bad_app_with_no_flag_stays_auto_negative():
    # A genuine bad recipe (no flag, no DEFERRED.md) is still auto-negative.
    td = generate_test_definition_from_hop3_toml(
        Path("apps/bad/real-apps-nix-bad/ghost"), {"metadata": {"id": "ghost"}}
    )
    assert td.expects_failure is True


# ---- scanner: DEFERRED.md business-drops are skipped (scoped to apps/bad) ----


def test_is_deferred_business_drop_predicate(tmp_path):
    cat = Catalog(root=tmp_path)

    # A deploys-fine business-drop: DEFERRED.md marked "not a platform
    # limitation" -> skipped.
    focal = tmp_path / "apps" / "bad" / "x" / "focal"
    focal.mkdir(parents=True)
    (focal / "DEFERRED.md").write_text(
        "**Business-reasons drop. Not a platform limitation.** Moved 2026-06-23."
    )
    assert cat._is_deferred_business_drop(focal) is True

    # A GENUINE bad recipe: DEFERRED.md documents a real blocker (it fails to
    # deploy) -> NOT skipped, stays a negative test. This is the verifier's
    # concern: an overloaded DEFERRED.md must not drop builder-rejection coverage.
    monica = tmp_path / "apps" / "bad" / "x" / "monica"
    monica.mkdir(parents=True)
    (monica / "DEFERRED.md").write_text(
        "## Blocker\n\nwebpack build fails; app does not deploy"
    )
    assert cat._is_deferred_business_drop(monica) is False

    ghost = tmp_path / "apps" / "bad" / "x" / "ghost"
    ghost.mkdir(parents=True)
    assert cat._is_deferred_business_drop(ghost) is False  # no DEFERRED.md -> kept

    # The business-drop marker OUTSIDE apps/bad does not trigger the skip.
    good = tmp_path / "apps" / "real-apps-native" / "z"
    good.mkdir(parents=True)
    (good / "DEFERRED.md").write_text("not a platform limitation")
    assert cat._is_deferred_business_drop(good) is False
