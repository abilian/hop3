# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
The admin commands teach a login that keeps the token off the command line.

They used to print ``hop3 login "SERVER_URL?token=<jwt>"``: copied as shown,
the token lands in shell history and in ``/proc/<pid>/cmdline``, where any
local user reads it.
"""

from __future__ import annotations

from pathlib import Path

from hop3.server.cli.admin import _print_login_hint

ADMIN_SOURCE = Path(__file__).parents[4] / "src/hop3/server/cli/admin.py"


def test_the_hint_uses_the_hidden_prompt(capsys):
    _print_login_hint()

    out = capsys.readouterr().out
    assert "hop3 login --url SERVER_URL --token\n" in out
    assert "?token=" not in out


def test_no_admin_command_prints_the_token_in_a_login_line():
    assert "?token=" not in ADMIN_SOURCE.read_text()
