# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""A refused call shows the server's reason, not just its status (ADR 061)."""

from __future__ import annotations

import httpx
from hop3_tui.api.client import http_error_message


def test_a_refusal_shows_the_servers_message():
    message = (
        "'hop3 env show' needs the deployer role; account 'vera' is viewer. "
        "An admin can grant it: hop3 user set-role vera deployer"
    )
    response = httpx.Response(
        403, json={"jsonrpc": "2.0", "error": {"code": -32003, "message": message}}
    )

    assert http_error_message(response) == message


def test_a_body_that_is_not_json_rpc_falls_back_to_the_status():
    assert http_error_message(httpx.Response(502, text="Bad gateway")) == (
        "HTTP error: 502"
    )
