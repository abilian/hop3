# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
A 401's case is read from `error.data.kind`, not from the server's prose.

The CLI decided whether to show the server's message by checking whether it
began "Authentication required": a reworded message would have changed what
users see. The prose check stays only for servers older than the field.
"""

from __future__ import annotations

from types import SimpleNamespace

from hop3_cli.rpc import Client
from hop3_cli.rpc.errors import server_error


def _response(message: str, kind: str | None = None) -> SimpleNamespace:
    error: dict = {"code": -32001, "message": message}
    if kind is not None:
        error["data"] = {"kind": kind}
    return SimpleNamespace(json=lambda: {"error": error})


def test_a_disabled_account_keeps_the_servers_explanation():
    message = "Your token names account 'dan', which is disabled on this server."
    assert Client._server_reason(_response(message, "account_unusable")) == message


def test_a_plain_sign_in_401_gets_the_clients_own_advice():
    reason = Client._server_reason(_response("Please sign in.", "unauthenticated"))
    assert reason == ""


def test_an_older_server_without_kind_falls_back_to_its_prose():
    assert Client._server_reason(_response("Authentication required. Use ...")) == ""
    assert Client._server_reason(_response("account 'x' is disabled")) == (
        "account 'x' is disabled"
    )


def test_server_error_tolerates_any_body():
    assert server_error("not json-rpc") == ("", "")
    assert server_error({"error": {"message": 3}}) == ("", "")
