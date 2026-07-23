# Copyright (c) 2023-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Test that the SSE stream controller enforces authentication.

Litestar's auth-guard invocation does not fire when the ASGI test client
is used (this is a known-limitation explicitly documented in
tests/b_integration/test_rpc_auth.py). A true end-to-end test would need
a running server. For unit-test purposes we assert the class-attribute
wiring so a refactor that accidentally drops the guards is caught.
"""

from __future__ import annotations

from hop3.server.controllers.stream import StreamController
from hop3.server.guards import auth_guard


def test_stream_controller_registers_auth_guard() -> None:
    """
    Regression test for the Wave 2 audit fix. Dropping this guard
    makes /api/stream/{id} unauthenticated, letting anyone spy on live
    deploy logs --- and those logs routinely contain tokens, env vars,
    and database URLs.
    """
    assert hasattr(StreamController, "guards"), (
        "StreamController must declare guards; deploy logs leak secrets"
    )
    assert auth_guard in StreamController.guards, (
        "StreamController.guards must include auth_guard"
    )
