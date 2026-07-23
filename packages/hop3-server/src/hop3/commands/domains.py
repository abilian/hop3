# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
CLI commands for managing an app's hostnames (domains).

These commands are a first-class view over the ``HOST_NAME`` env var that
the reverse-proxy plugins (nginx/caddy/traefik) read. The on-disk storage
remains ``HOST_NAME`` so the proxy plugins are unchanged.

All write operations are atomic: validate every input hostname and check
all conflicts up front, then apply.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from hop3.core.identifiers import InvalidIdentifierError, validate_hostname
from hop3.lib.args import parse_cli_args
from hop3.lib.registry import register

from ._base import Command, NamespaceCommand
from ._helpers import (
    check_hostname_conflict,
    get_app,
    parse_hostname_string,
    set_env_var,
    unset_env_var,
)
from ._response import error, hint, summary, table, text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from hop3.orm import App


# Rendered by the CLI with the user's own --context/--app (see _response.hint):
# {cmd} becomes e.g. `hop3 deploy --context prod`, so the suggested redeploy
# stays on the context the user is already targeting.
_REDEPLOY_HINT_MSG = (
    "\nNote: HOST_NAME changed. Run {cmd} to apply (affects proxy config)."
)


def _current_hosts(app: App) -> list[str]:
    for env_var in app.env_vars:
        if env_var.name == "HOST_NAME":
            return parse_hostname_string(env_var.value)
    return []


def _validate_new_hosts(hosts: list[str]) -> tuple[list[str], list[str]]:
    """
    Validate each hostname; return (valid_hosts, error_messages).

    Preserves order, deduplicates while keeping first occurrence.
    Rejects "_" combined with any other host.
    """
    errors: list[str] = []
    seen: set[str] = set()
    out: list[str] = []
    for raw in hosts:
        host = raw.strip()
        if not host or host in seen:
            continue
        try:
            validated = validate_hostname(host)
        except InvalidIdentifierError as e:
            errors.append(str(e))
            continue
        seen.add(validated)
        out.append(validated)

    if "_" in out and len(out) > 1:
        errors.append(
            "The catch-all hostname '_' cannot be combined with other hostnames."
        )
    return out, errors


def _persist(app: App, hosts: list[str], db_session: Session) -> None:
    """Write HOST_NAME from the canonical space-joined list. Empty list unsets."""
    if hosts:
        set_env_var(app, "HOST_NAME", " ".join(hosts))
    else:
        unset_env_var(app, "HOST_NAME")
    db_session.commit()


@register
class DomainsCmd(NamespaceCommand):
    """
    Manage hostnames bound to an application.

    Examples:
        hop3 domain list --app myapp
        hop3 domain add --app myapp example.com www.example.com
        hop3 domain remove --app myapp www.example.com
        hop3 domain set --app myapp example.com www.example.com
        hop3 domain clear --app myapp
    """

    name: ClassVar[tuple[str, ...]] = ("domain",)
    aliases: ClassVar[list[tuple[str, ...]]] = [("domains",)]


@register
@dataclass(frozen=True)
class ListCmd(Command):
    """
    List the hostnames currently bound to an app.

    Examples:
        hop3 domain list --app myapp
        hop3 domain list            # app from the current project/context
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("domain", "list")
    aliases: ClassVar[list[tuple[str, ...]]] = [("domains", "list")]
    _arg_spec: ClassVar[dict] = {
        "app": {"type": str},
        "_args": {"remaining": True},
    }

    def call(self, *args: str, **kwargs: object) -> list[dict]:
        parsed = parse_cli_args(args, self._arg_spec)
        app_name = parsed.get("app")
        if not app_name:
            return [text("Usage: hop3 domain list [--app <app>]")]

        app = get_app(self.db_session, app_name)
        hosts = _current_hosts(app)
        if not hosts:
            return [text(f"No domains set for '{app_name}'.")]
        return [
            text(f"Domains for '{app_name}':"),
            table(headers=["Hostname"], rows=[[h] for h in hosts]),
        ]


@register
@dataclass(frozen=True)
class AddCmd(Command):
    """
    Add one or more hostnames to an app (union, atomic).

    Examples:
        hop3 domain add --app myapp example.com
        hop3 domain add --app myapp example.com www.example.com
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("domain", "add")
    aliases: ClassVar[list[tuple[str, ...]]] = [("domains", "add")]
    _arg_spec: ClassVar[dict] = {
        "app": {"type": str},
        "_args": {"remaining": True},
    }

    def call(self, *args: str, **kwargs: object) -> list[dict]:
        parsed = parse_cli_args(args, self._arg_spec)
        app_name = parsed.get("app")
        new_inputs = list(parsed["_args"])

        if not app_name or not new_inputs:
            return [text("Usage: hop3 domain add [--app <app>] <host> [<host> ...]")]

        validated, errors = _validate_new_hosts(new_inputs)
        if errors:
            return [error("\n".join(errors))]

        app = get_app(self.db_session, app_name)
        current = _current_hosts(app)
        # Union, preserving order: current first, then new not-already-present.
        existing_set = set(current)
        added = [h for h in validated if h not in existing_set]
        if not added:
            return [text(f"All hostnames already set on '{app_name}'.")]

        merged = current + added
        if "_" in merged and len(merged) > 1:
            return [
                error(
                    "Refusing to combine '_' with other hostnames on "
                    f"'{app_name}'. Use 'hop3 domain set' to replace the list."
                )
            ]

        conflict = check_hostname_conflict(self.db_session, app_name, added)
        if conflict:
            other_app, other_host = conflict
            return [
                error(f"Hostname '{other_host}' is already used by app '{other_app}'")
            ]

        _persist(app, merged, self.db_session)

        result = [text(f"Added {len(added)} domain(s) to '{app_name}':")]
        result.extend(text(f"  + {h}") for h in added)
        result.append(hint("deploy", _REDEPLOY_HINT_MSG))
        result.append(summary(f"added {', '.join(added)} to {app_name}."))
        return result


@register
@dataclass(frozen=True)
class RemoveCmd(Command):
    """
    Remove one or more hostnames from an app (atomic).

    Errors if any of the requested hostnames is not currently set.

    Examples:
        hop3 domain remove --app myapp www.example.com
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("domain", "remove")
    aliases: ClassVar[list[tuple[str, ...]]] = [("domains", "remove")]
    _arg_spec: ClassVar[dict] = {
        "app": {"type": str},
        "_args": {"remaining": True},
    }

    def call(self, *args: str, **kwargs: object) -> list[dict]:
        parsed = parse_cli_args(args, self._arg_spec)
        app_name = parsed.get("app")
        targets = list(parsed["_args"])

        if not app_name or not targets:
            return [text("Usage: hop3 domain remove [--app <app>] <host> [<host> ...]")]

        app = get_app(self.db_session, app_name)
        current = _current_hosts(app)
        current_set = set(current)

        missing = [h for h in targets if h not in current_set]
        if missing:
            return [error(f"Hostname(s) not set on '{app_name}': {', '.join(missing)}")]

        target_set = set(targets)
        remaining_hosts = [h for h in current if h not in target_set]

        _persist(app, remaining_hosts, self.db_session)

        result = [text(f"Removed {len(targets)} domain(s) from '{app_name}':")]
        result.extend(text(f"  - {h}") for h in targets)
        result.append(hint("deploy", _REDEPLOY_HINT_MSG))
        result.append(summary(f"removed {', '.join(targets)} from {app_name}."))
        return result


@register
@dataclass(frozen=True)
class SetCmd(Command):
    """
    Replace the full list of hostnames for an app (atomic).

    Examples:
        hop3 domain set --app myapp example.com www.example.com
        hop3 domain set --app myapp example.com
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("domain", "set")
    aliases: ClassVar[list[tuple[str, ...]]] = [("domains", "set")]
    _arg_spec: ClassVar[dict] = {
        "app": {"type": str},
        "_args": {"remaining": True},
    }

    def call(self, *args: str, **kwargs: object) -> list[dict]:
        parsed = parse_cli_args(args, self._arg_spec)
        app_name = parsed.get("app")
        new_inputs = list(parsed["_args"])

        if not app_name or not new_inputs:
            return [text("Usage: hop3 domain set [--app <app>] <host> [<host> ...]")]

        validated, errors = _validate_new_hosts(new_inputs)
        if errors:
            return [error("\n".join(errors))]
        if not validated:
            return [
                error(
                    "No valid hostnames provided. Use 'hop3 domain clear' to "
                    "unset all domains."
                )
            ]

        conflict = check_hostname_conflict(self.db_session, app_name, validated)
        if conflict:
            other_app, other_host = conflict
            return [
                error(f"Hostname '{other_host}' is already used by app '{other_app}'")
            ]

        app = get_app(self.db_session, app_name)
        _persist(app, validated, self.db_session)

        result = [
            text(f"Set domains for '{app_name}':"),
            table(headers=["Hostname"], rows=[[h] for h in validated]),
        ]
        result.append(hint("deploy", _REDEPLOY_HINT_MSG))
        result.append(summary(f"set {', '.join(validated)} on {app_name}."))
        return result


@register
@dataclass(frozen=True)
class ClearCmd(Command):
    """
    Clear all hostnames from an app (unsets HOST_NAME).

    Examples:
        hop3 domain clear --app myapp
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("domain", "clear")
    aliases: ClassVar[list[tuple[str, ...]]] = [("domains", "clear")]
    _arg_spec: ClassVar[dict] = {
        "app": {"type": str},
        "_args": {"remaining": True},
    }

    def call(self, *args: str, **kwargs: object) -> list[dict]:
        parsed = parse_cli_args(args, self._arg_spec)
        app_name = parsed.get("app")
        if not app_name:
            return [text("Usage: hop3 domain clear [--app <app>]")]

        app = get_app(self.db_session, app_name)
        had = _current_hosts(app)
        if not had:
            return [text(f"No domains set for '{app_name}'.")]

        _persist(app, [], self.db_session)

        result = [text(f"Cleared {len(had)} domain(s) from '{app_name}'.")]
        result.append(hint("deploy", _REDEPLOY_HINT_MSG))
        result.append(summary(f"cleared HOST_NAME on {app_name}."))
        return result
