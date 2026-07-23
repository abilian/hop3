# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for command error formatting (hop3.commands._errors).

Focus: an Abort logs its full message at construction, so the wrapped error
must not repeat that detail when it was already streamed live to the client.
"""

from __future__ import annotations

from hop3.commands._errors import ErrorContext
from hop3.lib import Abort

_ACTIVE_STREAM = object()  # truthy stand-in for get_current_stream()


def test_abort_detail_carried_when_not_streaming(monkeypatch):
    # No active stream → the constructor log never reached the client, so the
    # wrapped message has to carry the detail.
    abort = Abort("Docker build failed: boom")  # construct before patching
    monkeypatch.setattr("hop3.server.streaming.get_current_stream", lambda: None)

    ctx = ErrorContext(operation="deploying app")
    assert ctx.format_error(abort) == "deploying app failed: Docker build failed: boom"


def test_abort_detail_not_repeated_when_streaming(monkeypatch):
    # A stream is active → Abort.__init__ already streamed the full detail live,
    # so the wrapped message stays concise (no double print).
    abort = Abort("Docker build failed: boom")  # construct before patching
    monkeypatch.setattr(
        "hop3.server.streaming.get_current_stream", lambda: _ACTIVE_STREAM
    )

    ctx = ErrorContext(operation="deploying app")
    assert ctx.format_error(abort) == "deploying app failed"


def test_non_abort_still_wrapped_with_detail(monkeypatch):
    # Plain exceptions never self-log, so they must always carry their detail —
    # regardless of streaming state.
    monkeypatch.setattr(
        "hop3.server.streaming.get_current_stream", lambda: _ACTIVE_STREAM
    )

    ctx = ErrorContext(operation="deploying app")
    assert ctx.format_error(RuntimeError("kaboom")) == "deploying app failed: kaboom"
