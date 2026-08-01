# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Every unauthenticated RPC command is a decision (audit 2026-07-29 F1).

`auth get-token` shipped with `requires_auth = False` and no throttle, so the
5/min limit on the web login form could be sidestepped by verifying the same
credentials over JSON-RPC instead. The defect was not the missing limiter call
-- it was that nothing forced anyone to think about it when the command was
written.

This test is that forcing function: a new `requires_auth = False` command must
either set `rate_limited = True` or be named below, and naming it means someone
asserted it verifies no credential.
"""

from __future__ import annotations

from hop3.commands import Command
from hop3.lib.registry import lookup
from hop3.server.controllers.rpc import is_rate_limited, requires_authentication

# Unauthenticated commands that verify no credential, so cost the caller
# nothing to guess at: help text and a version string. Add to this set only
# after checking the command touches no password, token, or secret.
UNTHROTTLED_PUBLIC_COMMANDS = {
    ("auth",),  # namespace, renders help
    ("help",),
    ("help", "commands"),
    ("version",),
}


def test_public_commands_are_throttled_or_explicitly_exempt() -> None:
    """A pre-auth command either costs bcrypt time or is a known freebie."""
    offenders = [
        cmd.name
        for cmd in lookup(Command)
        if not requires_authentication(cmd)
        and not is_rate_limited(cmd)
        and cmd.name not in UNTHROTTLED_PUBLIC_COMMANDS
    ]
    assert not offenders, (
        f"Unauthenticated commands with no rate limit: {offenders}. "
        "If the command verifies a credential, set `rate_limited = True`. "
        "If it cannot, add it to UNTHROTTLED_PUBLIC_COMMANDS."
    )


def test_get_token_is_rate_limited() -> None:
    """The command the finding was about, pinned by name."""
    by_name = {cmd.name: cmd for cmd in lookup(Command)}
    get_token = by_name["auth", "get-token"]
    assert not requires_authentication(get_token)
    assert is_rate_limited(get_token)
