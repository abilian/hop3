# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
The client's app-scope allowlist against the server's actual commands.

``APP_SCOPED_COMMANDS`` is a hand-maintained mirror of the commands registered
in ``hop3/commands/app.py``, and it drifts silently in a way users see: `hop3
app check --help` documented ``--app`` while the client refused the flag,
because the command had been added server-side and not there. The same guard
immediately found `app upgrade` and `app rollback`, which had been documenting
(and demonstrating) ``--app`` while the client rejected it.

Skipped whole when hop3-server is absent, so a standalone hop3-cli install has
nothing to compare against; in the workspace, where both are present, it runs.
"""

from __future__ import annotations

import inspect

import pytest
from hop3_cli.core.app_scope import APP_SCOPED_COMMANDS

pytest.importorskip("hop3.commands.app", reason="hop3-server is not installed")

from hop3.commands._base import Command
from hop3.lib.registry import lookup


def test_every_app_scoped_server_command_is_in_the_allowlist() -> None:
    """
    A server command that reads --app must be listed client-side, or it breaks.

    ``_resolve_app`` is the server-side marker: a handler that calls it takes
    its target from ``--app``, and the client only forwards that flag for
    commands it knows are app-scoped.
    """
    missing = []
    for command in lookup(Command):
        name = getattr(command, "name", ())
        if not (isinstance(name, tuple) and name[:1] == ("app",)):
            continue
        try:
            source = inspect.getsource(command.call)
        except (OSError, TypeError):
            continue
        if "_resolve_app" in source and name not in APP_SCOPED_COMMANDS:
            missing.append(name)

    assert not missing, (
        f"these `app` commands read --app server-side but are absent from "
        f"APP_SCOPED_COMMANDS, so the CLI refuses their --app flag: {missing}"
    )
