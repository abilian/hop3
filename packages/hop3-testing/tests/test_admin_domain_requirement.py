# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
A gated app needs an admin domain; the harness asks the server whether it has one.

`[access] require = "auth"` is refused at deploy on a server with no admin
domain, where there is nowhere to sign in. Running such a test there would
report the target, not the app, so the runner leaves it out, and says so. The
need is derived from the recipe, as services are from `[[addons]]`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hop3_testing.catalog.loader import generate_test_definition_from_hop3_toml
from hop3_testing.cli.runners import _filter_by_admin_domain
from hop3_testing.util.console import PrintingConsole

GATED = {"metadata": {"id": "gated"}, "access": {"require": "auth"}}
OPEN = {"metadata": {"id": "open"}}


def _test(data: dict):
    return generate_test_definition_from_hop3_toml(Path("apps/x"), data)


class _Target:
    """Answers `hop3-server admin:server-url` the way a server would."""

    def __init__(self, rc: int, out: str) -> None:
        self.rc, self.out = rc, out
        self.commands: list[str] = []

    def exec_run(self, command: str) -> tuple[int, str, str]:
        self.commands.append(command)
        return self.rc, self.out, "no such command" if self.rc else ""


def test_a_gated_app_needs_an_admin_domain():
    assert _test(GATED).requirements.admin_domain
    assert not _test(OPEN).requirements.admin_domain
    assert not _test({**OPEN, "access": {"require": "none"}}).requirements.admin_domain


def test_a_server_with_an_admin_domain_runs_every_test():
    tests = [_test(GATED), _test(OPEN)]
    target = _Target(0, "https://admin.example.com\n")
    assert _filter_by_admin_domain(tests, target, PrintingConsole()) == tests
    assert target.commands == [
        "sudo -u hop3 /home/hop3/venv/bin/hop3-server admin:server-url"
    ]


def test_a_server_without_one_leaves_the_gated_test_out(capsys):
    tests = [_test(GATED), _test(OPEN)]
    kept = _filter_by_admin_domain(tests, _Target(0, "\n"), PrintingConsole())
    assert [t.name for t in kept] == ["open"]
    assert "Skipping gated" in capsys.readouterr().out


def test_the_server_is_not_asked_when_no_test_needs_it():
    target = _Target(0, "")
    tests = [_test(OPEN)]
    assert _filter_by_admin_domain(tests, target, PrintingConsole()) == tests
    assert target.commands == []


def test_a_server_that_cannot_answer_fails_the_run():
    with pytest.raises(RuntimeError, match="admin:server-url"):
        _filter_by_admin_domain([_test(GATED)], _Target(1, ""), PrintingConsole())
