# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the reproducibility gate's pure logic."""

from __future__ import annotations

from hop3_tooling.nix_repro import interpret_rebuild, summarize


def test_clean_rebuild_is_reproducible():
    r = interpret_rebuild("miniflux", 0, "")
    assert r.reproducible


def test_determinism_mismatch_is_a_result_not_an_error():
    out = "error: hash mismatch in fixed-output derivation '/nix/store/...'"
    r = interpret_rebuild("isso", 1, out)
    assert not r.reproducible
    assert "deterministic" in r.detail


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
