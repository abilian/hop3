# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""The server's structured failure payload drives did-you-mean (ADR 036 D10)."""

from __future__ import annotations

import pytest
from hop3_cli.core.paths import commands_cache_path
from hop3_cli.rpc.responses import _scraped_suggestion, _structured_suggestion


def test_candidates_render_as_did_you_mean():
    out = _structured_suggestion({
        "kind": "unknown_command",
        "typed": "cataloig",
        "candidates": ["catalog"],
    })
    assert out is not None
    assert "catalog" in out


def test_app_candidates_render():
    out = _structured_suggestion({
        "kind": "unknown_app",
        "typed": "bugsnk",
        "candidates": ["bugsink", "bugsink2"],
    })
    assert out is not None
    assert "bugsink" in out


@pytest.mark.parametrize(
    "data",
    [
        None,
        "not a dict",
        {},
        {"kind": "unknown_app", "typed": "x", "candidates": []},
        # A hint-only payload: the server already spelled it out in the message.
        {"kind": "unknown_argument", "typed": "demo18", "hint": "--app demo18"},
    ],
)
def test_no_payload_no_suggestion(data):
    assert _structured_suggestion(data) is None


def test_scraped_fallback_is_still_reachable():
    """An older server sends no payload; the cached-command path still answers.

    The cache lands wherever ``$HOP3_CONFIG_DIR`` points, which the suite already
    sets per test. This used to plant a file under a monkeypatched ``$HOME`` and
    hope the resolver looked there — it did, because the cache path ignored the
    isolation lever entirely, and so read the developer's own cache in any test
    that did not set ``HOME``.
    """
    cache_path = commands_cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text("catalog list\ndeploy\n")

    out = _scraped_suggestion(-32601, "Command 'cataloig list' not found")

    assert out is not None
    assert "catalog list" in out
