# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Failures that carry their own candidates (ADR 036 D10)."""

from __future__ import annotations

import pytest

from hop3.lib.args import reject_extra_args
from hop3.lib.suggestions import (
    DidYouMeanError,
    SuggestionKind,
    closest_matches,
)


def test_closest_matches_finds_a_typo():
    matches = closest_matches("cataloig", ["catalog list", "catalog", "deploy"])
    assert matches[0] == "catalog"
    assert "deploy" not in matches


def test_closest_matches_is_empty_without_a_pool():
    assert closest_matches("cataloig", []) == []
    assert closest_matches("", ["catalog"]) == []


def test_payload_shape():
    err = DidYouMeanError(
        "boom", kind=SuggestionKind.UNKNOWN_APP, typed="bugsnk", candidates=["bugsink"]
    )
    assert err.data == {
        "kind": "unknown_app",
        "typed": "bugsnk",
        "candidates": ["bugsink"],
    }
    # A ValueError subclass, so callers that predate the payload still work.
    assert isinstance(err, ValueError)
    assert str(err) == "boom"


def test_hint_is_omitted_when_absent():
    err = DidYouMeanError("boom", kind=SuggestionKind.UNKNOWN_ARGUMENT, typed="x")
    assert "hint" not in err.data


def test_lone_positional_app_is_named_as_a_flag():
    """`hop3 app destroy demo18` must point at `--app demo18` (ADR 036 D5)."""
    with pytest.raises(DidYouMeanError) as exc_info:
        reject_extra_args(["demo18"])

    err = exc_info.value
    assert err.data["hint"] == "--app demo18"
    assert "--app demo18" in str(err)


def test_stray_flag_gets_no_app_hint():
    with pytest.raises(DidYouMeanError) as exc_info:
        reject_extra_args(["--no-addon"])

    assert "hint" not in exc_info.value.data
    assert "Unrecognized argument(s)" in str(exc_info.value)


def test_several_leftovers_get_no_app_hint():
    with pytest.raises(DidYouMeanError) as exc_info:
        reject_extra_args(["one", "two"])

    assert "hint" not in exc_info.value.data
