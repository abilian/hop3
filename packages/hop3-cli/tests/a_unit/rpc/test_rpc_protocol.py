# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""The client names the /rpc protocol it speaks."""

from __future__ import annotations

import json
from typing import Any

import requests
from hop3_cli.config import Config
from hop3_cli.rpc import Client
from hop3_cli.rpc.client import RPC_PROTOCOL_VERSION
from jsonrpcclient import Ok


class _Server:
    """``requests.post``: keeps each body, answers ``result``."""

    def __init__(self) -> None:
        self.bodies: list[dict] = []

    def __call__(self, url: str, *, data: Any, **_kwargs: Any) -> requests.Response:
        raw = data if isinstance(data, bytes) else b"".join(data)
        self.bodies.append(json.loads(raw))
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps({
            "jsonrpc": "2.0",
            "result": [],
            "id": self.bodies[-1]["id"],
        }).encode()
        return response


def test_the_protocol_is_sent(monkeypatch) -> None:
    server = _Server()
    monkeypatch.setattr("hop3_cli.rpc.client.requests.post", server)
    config = Config(
        data={
            "contexts": {"default": {"server": "http://localhost:8000"}},
            "cli": {"default_context": "default"},
        }
    )

    response = Client(config=config).rpc("cli", ["apps"])

    assert isinstance(response, Ok)
    assert server.bodies[0]["params"]["protocol"] == RPC_PROTOCOL_VERSION
