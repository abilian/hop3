# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""The run-result rows derive the packaging variant from the test's PATH.

The bare test_name (e.g. ``bugsink``) doesn't encode docker/native/nix, so two
variants of the same app were both shown as "other" and were indistinguishable.
"""

from __future__ import annotations

from types import SimpleNamespace

from hop3_testlab.web.controllers.runs import (
    _result_row,
)


def _rec(**kw) -> SimpleNamespace:
    base = {
        "id": 1,
        "test_name": "bugsink",
        "test_path": None,
        "category": "deployment",
        "priority": "P1",
        "passed": True,
        "status": "pass",
        "classification": None,
        "headline": None,
        "duration": 1.0,
        "error": None,
        "bundle_run_id": None,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def test_variant_comes_from_the_path() -> None:
    row = _result_row(_rec(test_path="apps/real-apps-docker/bugsink/hop3.toml"))
    assert row["variant"] == "docker"
    assert row["app"] == "bugsink"  # the short name still comes from test_name


def test_two_variants_of_one_app_are_distinct() -> None:
    docker = _result_row(_rec(test_path="apps/real-apps-docker/bugsink/hop3.toml"))
    native = _result_row(_rec(test_path="apps/real-apps-native/bugsink/hop3.toml"))
    nixgen = _result_row(_rec(test_path="apps/real-apps-nix-gen/bugsink/hop3.toml"))
    assert (docker["variant"], native["variant"], nixgen["variant"]) == (
        "docker",
        "native",
        "nix-template",
    )


def test_legacy_row_without_path_falls_back_to_other() -> None:
    # Pre-test_path records have no path, so the variant can't be recovered.
    assert _result_row(_rec(test_path=None))["variant"] == "other"
