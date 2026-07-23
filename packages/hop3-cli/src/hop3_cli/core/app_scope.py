# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Knowledge about which commands are app-scoped (ADR 036 D5/D7).

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
# Keep this in sync with the `app` command tuples registered server-side
# (hop3/commands/app.py). Notably the detail command is `app status`, not
# `app show` — the stale `show` entry left `hop3 app status` un-injected, so
# it alone demanded an explicit <app_name> while its siblings resolved one.
_APP_NAMESPACE_SCOPED: set[tuple[str, ...]] = {
    ("app", "destroy"),
    ("app", "status"),
    ("app", "ping"),
    ("app", "logs"),
    ("app", "build-logs"),
    ("app", "start"),
    ("app", "stop"),
    ("app", "restart"),
    ("app", "debug"),
    ("app", "sbom"),
    ("app", "credentials"),  # ADR 056: show an app's initial admin credential.
    ("app", "run"),  # canonical form of top-level `run` (alias). See run special-case.
    # ("app", "launch") and ("app", "list") are NOT app-scoped: launch creates
    # an app from a repo arg; list takes no app.
    # ("app", "rename") — second arg is the new name, not a second app; app is positional and unambiguous
}

# Env-var commands (all operate on a single app's environment).
# `config` is the back-compat alias; the client sees whichever the user typed,
# so both ("env", X) and ("config", X) must be app-scoped. The bare namespace
# is intentionally absent: `hop3 env` / `hop3 config` shows namespace help and
# must not error out demanding an app. `migrate` takes a path, not an app.
_ENV_SCOPED: set[tuple[str, ...]] = {
    ("env", "show"),
    ("env", "get"),
    ("env", "set"),
    ("env", "unset"),
    ("env", "live"),
}
_CONFIG_SCOPED: set[tuple[str, ...]] = {("config", *rest) for (_, *rest) in _ENV_SCOPED}

# Addon attach/detach bind an addon to a single app — the app is the `--app`
# target. They MUST be app-scoped: `parse_flags` strips the user's `--app` into
# `flags.app`, and only app-scoped commands get it re-injected into the forwarded
# argv. Without these entries the explicit `--app` is silently dropped and the
# server rejects the call with "--app parameter is required". (`addon create` /
# `destroy` / `show` / `list` operate on the addon, not an app — not scoped.)
_ADDON_SCOPED: set[tuple[str, ...]] = {
    ("addon", "attach"),
    ("addon", "detach"),
}

# Backup commands.
_BACKUP_SCOPED: set[tuple[str, ...]] = {
    ("backup", "create"),
    # Note: `backup list --app X` is app-scoped; bare `backup list` lists all.
    # We don't auto-inject here; explicit --app is fine.
    # Restore: `backup restore <id>` target app comes from the backup metadata or --app.
    # Treat like backup create: injection allowed but optional.
}

# Domain commands (each manages a single app's hostnames). The app is the
# `--app` flag; the positionals are hostnames. `domains` is the alias the
# client may also send. The bare namespace is absent (it shows help).
_DOMAIN_SCOPED: set[tuple[str, ...]] = {
    ("domain", "add"),
    ("domain", "remove"),
    ("domain", "set"),
    ("domain", "clear"),
    ("domain", "list"),
}
_DOMAINS_SCOPED: set[tuple[str, ...]] = {
    ("domains", *rest) for (_, *rest) in _DOMAIN_SCOPED
}

# `catalog install <blueprint-id> --app <name>` names the NEW app via --app; it
# must be app-scoped so the client forwards --app (parse_flags strips it into
# flags.app, and only app-scoped commands get it re-injected). The <blueprint-id>
# is a catalog identifier positional, not an app. (Bare `catalog list`/`refresh`
# are not app-scoped.)
_CATALOG_SCOPED: set[tuple[str, ...]] = {
    ("catalog", "install"),
}

APP_SCOPED_COMMANDS: set[tuple[str, ...]] = (
    _TOP_LEVEL_APP_SCOPED
    | _APP_NAMESPACE_SCOPED
    | _ENV_SCOPED
    | _CONFIG_SCOPED
    | _ADDON_SCOPED
    | _BACKUP_SCOPED
    | _DOMAIN_SCOPED
    | _DOMAINS_SCOPED
    | _CATALOG_SCOPED
)

# Create-style commands whose --app names a *new* app, not an existing target.
# They stay in APP_SCOPED_COMMANDS so an EXPLICIT --app is still forwarded to the
# server (parse_flags strips it into flags.app), but the client must NOT resolve
# and inject an AMBIENT app as that name when --app is omitted — the server
# requires it explicitly. (Mirrors why `app launch` is not app-scoped at all: its
# target is a new name, never an ambient/existing app.)
NEW_APP_SCOPED_COMMANDS: set[tuple[str, ...]] = _CATALOG_SCOPED


_MAX_DEPTH = max((len(t) for t in APP_SCOPED_COMMANDS), default=1)


def is_app_scoped(cli_args: list[str]) -> tuple[bool, int]:
    """
    Check if the command in cli_args is app-scoped.

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
