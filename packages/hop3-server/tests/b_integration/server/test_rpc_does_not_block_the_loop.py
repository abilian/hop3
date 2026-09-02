# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
An RPC command must not execute on the event loop thread.

`handle_rpc` was `async def` and called the fully synchronous
`_execute_command` inline, so a command that shells out — `backup create`,
`app stop`, `cert issue` — ran to completion *on the event loop*. With a
single worker (server/cli/serve.py) that froze authentication, the dashboard
and every SSE deploy stream for the command's whole duration.

Asserting "another request stays fast" through TestClient does not work: it
drives each call through its own portal, so the contention never materialises
and the test passes with the bug present. What *is* observable, and is exactly
the fix, is which thread the command body runs on.
"""

from __future__ import annotations

import asyncio
import threading

import pytest
from litestar.testing import TestClient

import hop3.config
from hop3.orm import get_session_factory
from hop3.orm.session import reset_session_factory_cache
from hop3.server.asgi import create_app
from hop3.server.controllers import rpc as rpc_module


@pytest.fixture
def client(monkeypatch, worker_id, request):
    slug = f"{worker_id}_{abs(hash(request.node.nodeid)) % 10**8}"
    monkeypatch.setenv(
        "HOP3_DATABASE_URI",
        f"sqlite:///file:memdb_{slug}?mode=memory&cache=shared&uri=true",
    )
    reset_session_factory_cache()
    get_session_factory()
    monkeypatch.setattr(hop3.config, "HOP3_UNSAFE", True)
    yield TestClient(create_app())
    reset_session_factory_cache()


def _rpc(client, monkeypatch) -> dict:
    """Run one command, capturing where its body executed."""
    seen: dict = {}

    def record(self, command_name, args, extra_args, request_id):
        seen["thread"] = threading.current_thread().ident
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            seen["on_loop"] = False
        else:
            seen["on_loop"] = True
        return self._build_success_response([], request_id)

    monkeypatch.setattr(rpc_module.RPCController, "_execute_command", record)
    response = client.post(
        "/rpc/",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "cli",
            "params": {"cli_args": ["help"], "extra_args": {}},
        },
    )
    assert response.status_code == 200
    return seen


def test_the_command_body_does_not_run_on_the_event_loop(client, monkeypatch):
    seen = _rpc(client, monkeypatch)

    assert seen["on_loop"] is False, (
        "the command ran on the event loop thread; a command that shells out "
        "would freeze auth, the dashboard and every SSE stream while it ran"
    )


def test_the_command_still_returns_its_response(client, monkeypatch):
    # Offloading must not change what the caller gets back.
    seen = _rpc(client, monkeypatch)
    assert "thread" in seen
