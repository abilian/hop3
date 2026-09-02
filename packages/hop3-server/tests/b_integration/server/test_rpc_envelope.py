# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
A malformed JSON-RPC envelope gets a JSON-RPC error, not an HTML 500.

Every member of the envelope used to be read unguarded — `data["method"]`,
`data["params"]`, `params["cli_args"]` — so a wrong-shaped body raised
KeyError/TypeError and Litestar answered with `{"detail": "Internal Server
Error"}` at HTTP 500, which no JSON-RPC client can interpret. The method check
was an `assert`, which additionally disappears under `python -O`.
"""

from __future__ import annotations

import pytest
from litestar.testing import TestClient

import hop3.config
from hop3.orm import get_session_factory
from hop3.orm.session import reset_session_factory_cache
from hop3.server.asgi import create_app


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


def _error(response) -> dict:
    body = response.json()
    assert "error" in body, f"expected a JSON-RPC error, got {body}"
    return body["error"]


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"jsonrpc": "2.0", "id": 7}, -32601),  # no method
        ({"jsonrpc": "2.0", "id": 7, "method": "nope", "params": {}}, -32601),
        ({"jsonrpc": "2.0", "id": 7, "method": "cli"}, -32602),  # no params
        ({"jsonrpc": "2.0", "id": 7, "method": "cli", "params": []}, -32602),
        ({"jsonrpc": "2.0", "id": 7, "method": "cli", "params": {}}, -32602),
        (
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "cli",
                "params": {"cli_args": "help"},
            },
            -32602,
        ),
        (
            {"jsonrpc": "2.0", "id": 7, "method": "cli", "params": {"cli_args": []}},
            -32602,
        ),
        (
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "cli",
                "params": {"cli_args": ["help"], "extra_args": "no"},
            },
            -32602,
        ),
        (
            {"jsonrpc": "1.0", "id": 7, "method": "cli", "params": {"cli_args": ["x"]}},
            -32600,
        ),
    ],
)
def test_malformed_envelope_returns_a_jsonrpc_error(client, payload, code):
    response = client.post("/rpc/", json=payload)

    assert response.status_code != 500, "malformed envelope produced an HTML 500"
    assert _error(response)["code"] == code


def test_the_error_echoes_the_callers_id(client):
    response = client.post(
        "/rpc/", json={"jsonrpc": "2.0", "id": 4242, "method": "nope", "params": {}}
    )
    assert response.json()["id"] == 4242


def test_a_valid_envelope_still_works(client):
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
    assert "error" not in response.json()


def test_method_check_is_not_an_assert(client):
    """
    It was an `assert`, so `python -O` skipped it entirely and any method
    string was accepted. Asserting the behaviour, not the implementation.
    """
    response = client.post(
        "/rpc/",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "definitely-not-cli",
            "params": {"cli_args": ["help"], "extra_args": {}},
        },
    )
    assert _error(response)["code"] == -32601
