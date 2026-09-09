# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The docs CLI linter must not call the supported short forms deprecated.

It told a reader that `hop3 apps` and `hop3 login` — the spellings people type
every day — were obsolete. Two different things had been merged under one
label: the server-side table keys that are a rename's old spelling (`config` ->
`env`), which the docs should stop teaching, and `CORE_ALIASES`, which is the
deliberate short-form surface of ADR 036 D9. Only the first is deprecated.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "lint_cli_commands.py"


@pytest.fixture(scope="module")
def linter():
    spec = importlib.util.spec_from_file_location("lint_cli_commands", SCRIPT)
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def surface(linter):
    return linter.load_surface()


def check(linter, surface, line: str):
    """(reason, suggestion) for one invocation, or None when it is fine."""
    tokens = linter.command_tokens(line)
    return linter.check_invocation(tokens, surface)


# ADR 036 D9's short-form surface: plural list shortcuts, the `whoami` synonym,
# the short `login`/`logout`, and `ssh`, which D2 *reserves* as a top-level verb.
@pytest.mark.parametrize(
    "invocation",
    [
        "apps",
        "addons",
        "whoami",
        "login --ssh root@host",
        "logout",
        "ssh --app demo",
    ],
)
def test_supported_short_forms_are_not_flagged(linter, surface, invocation):
    assert check(linter, surface, invocation) is None


# A table key that is not the command's own name is a rename's old spelling.
@pytest.mark.parametrize(
    ("invocation", "canonical"),
    [
        ("config set FOO=bar", "env set"),
        ("domains list", "domain list"),
    ],
)
def test_renamed_spellings_are_still_flagged(linter, surface, invocation, canonical):
    result = check(linter, surface, invocation)
    assert result is not None, f"{invocation!r} should still be reported"
    reason, suggestion = result
    assert reason == linter.DEPRECATED_ALIAS
    assert suggestion == canonical


def test_unknown_command_is_still_an_error(linter, surface):
    result = check(linter, surface, "frobnicate")
    assert result is not None
    assert result[0] != linter.DEPRECATED_ALIAS


def test_a_trailing_shell_comment_is_not_part_of_the_command(linter):
    """`hop3 apps  # ask dev` was reported as the invocation `apps # ask dev`."""
    assert linter.command_tokens("apps  # ask the one you named") == ["apps"]
    assert linter.command_tokens("logout  # revoke this machine's token") == ["logout"]
