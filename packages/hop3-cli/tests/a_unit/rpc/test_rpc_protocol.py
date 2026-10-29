# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""The client names the /rpc protocol it speaks, and still talks to older servers."""

from __future__ import annotations

import json
from typing import Any

import pytest
import requests
from hop3_cli.config import Config
from hop3_cli.rpc import Client
from hop3_cli.rpc.client import PROTOCOL_HEADER, RPC_PROTOCOL_VERSION
from jsonrpcclient import Ok


class _Server:
    """``requests.post``: keeps each body, answers ``result`` with ``headers``."""

    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers
        self.bodies: list[dict] = []

    def __call__(self, url: str, *, data: Any, **_kwargs: Any) -> requests.Response:
        raw = data if isinstance(data, bytes) else b"".join(data)
        self.bodies.append(json.loads(raw))
        response = requests.Response()
        response.status_code = 200
        response.headers.update(self.headers)
        response._content = json.dumps({
            "jsonrpc": "2.0",
            "result": [],
            "id": self.bodies[-1]["id"],
        }).encode()
        return response


@pytest.mark.parametrize(
    "headers",
    [{PROTOCOL_HEADER: str(RPC_PROTOCOL_VERSION)}, {}],  # current, older server
)
def test_the_protocol_is_sent_and_an_older_server_still_answers(
    monkeypatch, headers
) -> None:
    server = _Server(headers)
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
