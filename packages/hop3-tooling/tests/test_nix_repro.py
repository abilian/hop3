# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the reproducibility gate's pure logic."""

from __future__ import annotations

from pathlib import Path

import click
import pytest
import tomllib
from hop3_tooling.cli import _pin_override, _with_pin
from hop3_tooling.nix_repro import (
    Outcome,
    classify,
    interpret_rebuild,
    summarize,
)

from hop3.plugins.build.nix.gen.toml_adapter import app_spec_from_config


def test_clean_rebuild_is_reproducible():
    r = interpret_rebuild("miniflux", 0, "")
    assert r.reproducible


def test_a_stale_pinned_hash_is_not_a_determinism_defect():
    """
    A fixed-output mismatch means the *pinned* hash no longer matches — the
    ordinary outcome of moving the nixpkgs pin, and mechanical to fix. Reporting
    it as non-determinism sends you hunting a bug that isn't there.
    """
    out = "error: hash mismatch in fixed-output derivation '/nix/store/...'"
    r = interpret_rebuild("isso", 1, out)
    assert not r.reproducible
    assert r.outcome is Outcome.STALE_HASH


def test_may_not_be_deterministic_wording():
    out = (
        "error: derivation '/nix/store/x.drv' may not be deterministic: output differs"
    )
    assert not interpret_rebuild("x", 1, out).reproducible


def test_unrelated_build_failure_is_not_counted_as_reproducible():
    """A build that fell over for another reason must not read as a pass."""
    r = interpret_rebuild("gitea", 1, "error: disk full while unpacking")
    assert not r.reproducible
    assert "build failed" in r.detail


def test_summary_reports_the_offenders():
    results = [
        interpret_rebuild("a", 0, ""),
        interpret_rebuild("b", 1, "output 'x' differs"),
    ]
    ok, msg = summarize(results)
    assert not ok
    assert "b" in msg


def test_all_reproducible_passes():
    ok, msg = summarize([interpret_rebuild("a", 0, ""), interpret_rebuild("b", 0, "")])
    assert ok
    assert "all 2" in msg


def test_empty_is_a_failure_not_a_vacuous_pass():
    """A gate that checked nothing must not report success."""
    ok, msg = summarize([])
    assert not ok
    assert "no apps" in msg


def test_an_upstream_attribute_that_vanished_is_its_own_category():
    """
    Bumping the pin to nixos-25.11 removed ruby_3_2 — no hash re-derivation
    fixes that; it needs a human to pick a replacement.
    """
    for out in (
        "error: attribute 'ruby_3_2' missing",
        "error: ruby_3_2 has been removed",
        "error: undefined variable 'pnpm_9'",
    ):
        assert classify(out) is Outcome.EVAL_ERROR


def test_the_summary_groups_by_disposition_and_names_the_remedy():
    results = [
        interpret_rebuild("ok-app", 0, ""),
        interpret_rebuild("isso", 1, "error: hash mismatch in fixed-output derivation"),
        interpret_rebuild(
            "bugsink", 1, "error: hash mismatch in fixed-output derivation"
        ),
        interpret_rebuild("redmine", 1, "error: attribute 'ruby_3_2' missing"),
    ]
    ok, summary = summarize(results)
    assert not ok
    assert "3 of 4 not reproducible" in summary
    assert "2 stale hash" in summary
    assert "vendor-hash" in summary  # the remedy, not just the verdict
    assert "1 eval error" in summary
    assert "isso, bugsink" in summary


# --- the pin override (a bump must be expressible without editing 31 files) ---


def test_pin_override_requires_both_halves():
    assert _pin_override(None, None) is None
    assert _pin_override("a" * 40, "sha256-x") == ("a" * 40, "sha256-x")
    with pytest.raises(click.ClickException, match="must be given together"):
        _pin_override("a" * 40, None)


def test_pin_override_replaces_whatever_the_recipe_declares():
    """
    etherpad pins itself to a 25.05 rev. A corpus-wide bump has to override
    that too, or the run silently measures two different nixpkgs.
    """
    config = tomllib.loads(
        Path("apps/real-apps-nix-gen/etherpad/hop3.toml").read_text()
    )
    spec = app_spec_from_config(config["nix"], config.get("metadata") or {}, "etherpad")
    assert spec.nixpkgs_rev  # the recipe carries its own pin

    bumped = _with_pin(spec, ("c" * 40, "sha256-bumped"))
    assert bumped.nixpkgs_rev == "c" * 40
    assert _with_pin(spec, None).nixpkgs_rev == spec.nixpkgs_rev
