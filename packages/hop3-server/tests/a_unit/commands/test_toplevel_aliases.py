# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Top-level daily verbs resolve to their `app` namespace commands.

These were listed as app-scoped client-side but only `destroy`/`run` were
wired server-side, so `hop3 status myapp` / `logs` / `restart` used to fail
with "Command not found".
"""

from __future__ import annotations

import pytest

from hop3.lib.scanner import scan_package
from hop3.server.controllers.rpc import find_command


@pytest.fixture(scope="module", autouse=True)
def _register():
    scan_package("hop3.commands")


@pytest.mark.parametrize(
    ("verb", "canonical"),
    [
        ("status", ("app", "status")),
        ("logs", ("app", "logs")),
        ("restart", ("app", "restart")),
        ("destroy", ("app", "destroy")),
        ("run", ("app", "run")),
    ],
)
def test_toplevel_verb_resolves_to_app_command(verb, canonical):
    cls, _ = find_command([verb, "myapp"])
    assert cls is not None, verb
    assert cls.name == canonical
