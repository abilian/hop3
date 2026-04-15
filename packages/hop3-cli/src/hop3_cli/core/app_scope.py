# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Knowledge about which commands are app-scoped (ADR 036 D5/D7).

For M2, we hardcode the set of app-scoped commands so the client can (a) know
when to resolve an implicit app and (b) inject the resolved app into the
argv stream as the first positional after the command name. A future milestone
(see ADR 039) will have plugins declare app-scoped-ness in their manifest and
the server expose it via `help commands`.

The set uses tuple command names per D1/D18. Longer entries take precedence
when a command name is a prefix of another.
"""

from __future__ import annotations

# Top-level daily verbs. All operate on one app (D2 rule 1).
_TOP_LEVEL_APP_SCOPED: set[tuple[str, ...]] = {
    ("deploy",),
    ("logs",),
    ("run",),
    ("restart",),
    ("status",),
    ("ps",),
    ("scale",),
    ("ssh",),
    ("open",),
    # ("exec",) — deferred per Q5
}

# Management verbs in the `app` namespace that take an app target.
_APP_NAMESPACE_SCOPED: set[tuple[str, ...]] = {
    ("app", "destroy"),
    ("app", "show"),
    ("app", "ping"),
    ("app", "logs"),
    ("app", "build-logs"),
    ("app", "start"),
    ("app", "stop"),
    ("app", "restart"),
    ("app", "env"),
    ("app", "debug"),
    ("app", "sbom"),
    # ("app", "rename") — second arg is the new name, not a second app; app is positional and unambiguous
}

# Config commands (all operate on a single app's config).
_CONFIG_SCOPED: set[tuple[str, ...]] = {
    ("config",),             # bare shows namespace help — still app-scoped when user intends a list
    ("config", "show"),
    ("config", "get"),
    ("config", "set"),
    ("config", "unset"),
    ("config", "live"),
    ("config", "migrate"),
}

# Backup commands.
_BACKUP_SCOPED: set[tuple[str, ...]] = {
    ("backup", "create"),
    # Note: `backup list --app X` is app-scoped; bare `backup list` lists all.
    # We don't auto-inject here; explicit --app is fine.
    # Restore: `backup restore <id>` target app comes from the backup metadata or --app.
    # Treat like backup create: injection allowed but optional.
}

APP_SCOPED_COMMANDS: set[tuple[str, ...]] = (
    _TOP_LEVEL_APP_SCOPED
    | _APP_NAMESPACE_SCOPED
    | _CONFIG_SCOPED
    | _BACKUP_SCOPED
)


_MAX_DEPTH = max((len(t) for t in APP_SCOPED_COMMANDS), default=1)


def is_app_scoped(cli_args: list[str]) -> tuple[bool, int]:
    """Check if the command in cli_args is app-scoped.

    Returns (True, n_consumed) where n_consumed is the number of tokens that
    form the command name. Returns (False, 0) if the command is not app-scoped
    (or is empty).
    """
    if not cli_args:
        return False, 0
    for n in range(min(len(cli_args), _MAX_DEPTH), 0, -1):
        if tuple(cli_args[:n]) in APP_SCOPED_COMMANDS:
            return True, n
    return False, 0
