# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Regression tests for the ``run_as_hop3`` shell seam.

``su -c`` hands its argument to a login shell, so every value reaching it is
shell-parsed whether the caller wants that or not. ``run_as_hop3`` takes an
argv list and quotes it at the seam, which makes the invariant a property of
the function instead of a rule ~20 call sites have to remember.

See ``notes/security/security-model.md`` §3.2.5 and
``notes/security/report-2026-07.md`` finding 3.
"""

from __future__ import annotations

import shlex
from unittest.mock import patch

import pytest
from hop3_installer.server_installer.user import run_as_hop3, run_as_hop3_shell

# Values that would break out of, or corrupt, an unquoted shell word.
HOSTILE_ARGS = [
    "a b",  # word splitting
    "x; whoami",  # command separator
    "x && whoami",  # conditional chain
    "x | whoami",  # pipe
    "$(whoami)",  # command substitution
    "`whoami`",  # legacy command substitution
    "x\nwhoami",  # newline injection
    "'quoted'",  # embedded quotes
    "*",  # glob
]


@pytest.fixture
def spy():
    """Capture the argv handed to run_cmd, without spawning anything."""
    with patch("hop3_installer.server_installer.user.run_cmd") as mock:
        yield mock


def _script(spy) -> str:
    """The shell script `su -c` was asked to run."""
    argv = spy.call_args[0][0]
    assert argv[:4] == ["su", "-", "hop3", "-c"]
    return argv[4]


@pytest.mark.parametrize("hostile", HOSTILE_ARGS)
def test_argv_elements_survive_as_single_words(spy, hostile: str) -> None:
    """A hostile argument reaches the shell as one literal word."""
    run_as_hop3(["echo", hostile])

    # The definitive check: the login shell splits the script back into exactly
    # the argv we passed, so the hostile value arrives intact and inert -- one
    # argument to echo, not a second command.
    assert shlex.split(_script(spy)) == ["echo", hostile]


def test_plain_command_is_readable(spy) -> None:
    """Quoting must not mangle ordinary commands (they end up in logs)."""
    run_as_hop3(["nix", "--version"])
    assert _script(spy) == "nix --version"


def test_shell_variant_passes_the_script_through(spy) -> None:
    """The escape hatch runs its script verbatim -- the caller owns quoting."""
    script = "cat /etc/foo 2>/dev/null || true"
    run_as_hop3_shell(script)
    assert _script(spy) == script


def test_kwargs_reach_run_cmd(spy) -> None:
    """check/timeout are forwarded, not silently dropped."""
    run_as_hop3(["true"], check=True, timeout=42)
    assert spy.call_args.kwargs == {"check": True, "timeout": 42}


def test_no_call_site_passes_a_bare_string() -> None:
    """
    A string argument is a migration slip: ``shlex.join`` would iterate it
    character by character and silently produce a mangled command.
    """
    with pytest.raises(TypeError, match="takes a list"):
        run_as_hop3("pip install foo")  # type: ignore[arg-type]
