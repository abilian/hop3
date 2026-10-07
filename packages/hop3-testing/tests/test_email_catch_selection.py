# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
The harness switches a server to the `catch` email backend only when it has
nothing to restore afterwards.

It switched unconditionally and never switched back: on a `--host` server
that replaced the operator's mail relay for every app on the box.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from hop3_testing.cli import runners


def _status(backend: str) -> str:
    return json.dumps([
        {"t": "warning", "text": "EXPERIMENTAL"},
        {"t": "table", "headers": ["Field", "Value"], "rows": [["backend", backend]]},
    ])


class _Target:
    """Answers the commands `_select_email_catch` runs, records them."""

    def __init__(self, backend: str) -> None:
        self.backend = backend
        self.commands: list[str] = []

    def exec_run(self, cmd):
        self.commands.append(cmd)
        if "status --json" in cmd:
            return 0, _status(self.backend), ""
        if "email status" in cmd:
            return 0, "sink  Mailpit on 127.0.0.1:1025, answering", ""
        return 0, "", ""


def _email_tests():
    return [SimpleNamespace(requirements=SimpleNamespace(services=["email"]))]


def _console():
    return SimpleNamespace(status=lambda _msg: None)


def test_an_operator_relay_is_never_replaced():
    target = _Target("relay")

    with pytest.raises(RuntimeError, match="'relay'"):
        runners._select_email_catch(_email_tests(), target, _console())

    assert not any("backend catch" in c for c in target.commands)


@pytest.mark.parametrize(
    "backend", ["none", "catch (mail is captured, never delivered)"]
)
def test_an_unset_or_catch_backend_is_switched(backend):
    target = _Target(backend)

    runners._select_email_catch(_email_tests(), target, _console())

    assert any("backend catch" in c for c in target.commands)
