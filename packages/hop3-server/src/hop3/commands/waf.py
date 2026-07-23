# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
CLI commands for the Layer-7 WAF (ADR 050 §9) — ban runtime state.

Bans are operator-visible runtime state: ``hop3 waf bans list`` shows who's
currently cut off and why, ``hop3 waf bans clear`` lifts a ban, and
``hop3 waf reconcile-bans`` is a manual entry point to the scorer that turns the
WAF audit stream into bans. The server runs that same scorer in-process on a
timer (``waf_bans_service``); the CLI command is the on-demand fallback. The
declarative policy (``[waf]`` in hop3.toml) is not managed here — only the
runtime ban state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from hop3 import config as c
from hop3.core.plugins import get_waf_engine
from hop3.deployers.waf import _read_audit, reconcile_bans, reload_proxy
from hop3.lib.registry import register
from hop3.orm import AppRepository, BanRepository
from hop3.waf.bans import utcnow

from ._base import Command
from ._response import error, summary, table, text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# Default number of audit entries `hop3 waf logs` shows.
_LOG_TAIL = 50


@register
@dataclass(frozen=True)
class WafStatusCmd(Command):
    """
    Show WAF status: per-app proxy port, supervision, and active ban count.

    Examples:
        hop3 waf status
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("waf", "status")

    def call(self, *args):
        if args:
            return [text("Usage: hop3 waf status")]
        apps = AppRepository(session=self.db_session).list_all_ordered()
        waf_apps = [a for a in apps if a.waf_port]
        if not waf_apps:
            return [text("No apps have the WAF enabled.")]
        ban_repo = BanRepository(session=self.db_session)
        now = utcnow()
        rows = []
        for app in waf_apps:
            vassal = c.UWSGI_ENABLED / f"{app.name}_waf.1.ini"
            rows.append([
                app.name,
                str(app.waf_port),
                "supervised" if vassal.exists() else "stopped",
                str(len(ban_repo.list_active(app.id, now))),
            ])
        return [table(headers=["App", "Proxy port", "Proxy", "Active bans"], rows=rows)]


@register
@dataclass(frozen=True)
class WafLogsCmd(Command):
    """
    Show recent WAF audit entries (blocked requests) — surfaced where the
    operator looks, never only in a file.

    Examples:
        hop3 waf logs            # recent entries across all WAF-enabled apps
        hop3 waf logs myapp      # just one app
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("waf", "logs")

    def call(self, *args):
        if len(args) > 1:
            return [text("Usage: hop3 waf logs [<app>]")]
        app_filter = args[0] if args else None
        apps = AppRepository(session=self.db_session).list_all_ordered()
        targets = [
            a
            for a in apps
            if a.waf_port and (app_filter is None or a.name == app_filter)
        ]
        if app_filter and not targets:
            return [error(f"No WAF-enabled app named '{app_filter}'.")]

        engine = get_waf_engine()
        entries = []
        for app in targets:
            for record in _read_audit(engine.audit_path(app.name)):
                record["app"] = app.name
                entries.append(record)
        entries.sort(key=lambda e: e.get("timestamp", ""))
        recent = entries[-_LOG_TAIL:]
        if not recent:
            return [text("No WAF audit entries.")]
        rows = [
            [
                e.get("timestamp", ""),
                e.get("app", ""),
                e.get("client_ip", ""),
                e.get("action", ""),
                str(e.get("rule_id", "")),
                e.get("request_uri", ""),
            ]
            for e in recent
        ]
        return [
            table(
                headers=["Time (UTC)", "App", "Source", "Action", "Rule", "Path"],
                rows=rows,
            )
        ]


@register
@dataclass(frozen=True)
class WafBansListCmd(Command):
    """
    List active WAF bans (optionally for one app).

    Examples:
        hop3 waf bans list
        hop3 waf bans list myapp
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("waf", "bans", "list")

    def call(self, *args):
        if len(args) > 1:
            return [text("Usage: hop3 waf bans list [<app>]")]
        app_filter = args[0] if args else None
        bans = BanRepository(session=self.db_session).list_all_active(utcnow())
        if app_filter:
            bans = [b for b in bans if b.app_name == app_filter]
        if not bans:
            return [text("No active WAF bans.")]
        rows = [
            [
                b.app_name,
                b.source,
                b.reason,
                b.expires_at.isoformat(sep=" ", timespec="seconds"),
            ]
            for b in bans
        ]
        return [table(headers=["App", "Source", "Reason", "Expires (UTC)"], rows=rows)]


@register
@dataclass(frozen=True)
class WafBansClearCmd(Command):
    """
    Lift WAF bans for an app — all of them, or one source IP.

    Rewrites the app's denylist and reloads the proxy so the change takes effect.

    Examples:
        hop3 waf bans clear myapp              # clear all bans for myapp
        hop3 waf bans clear myapp 198.51.100.9 # clear one source
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("waf", "bans", "clear")
    destructive: ClassVar[bool] = True

    def call(self, *args):
        if not (1 <= len(args) <= 2):
            return [text("Usage: hop3 waf bans clear <app> [<ip>]")]
        app_name = args[0]
        source = args[1] if len(args) > 1 else None

        app = AppRepository(session=self.db_session).get_by_name(app_name)
        if app is None:
            return [error(f"No app named '{app_name}'.")]
        repo = BanRepository(session=self.db_session)
        bans = repo.list_for_app(app.id)
        if source:
            bans = [b for b in bans if b.source == source]
        if not bans:
            return [text(f"No matching bans for '{app_name}'.")]

        for ban in bans:
            self.db_session.delete(ban)
        self.db_session.flush()

        # Regenerate the denylist from what remains active and reload the proxy
        # (only if the denylist content actually changed).
        active = sorted(b.source for b in repo.list_active(app.id, utcnow()))
        if get_waf_engine().write_bans(app_name, active):
            reload_proxy(app_name)
        self.db_session.commit()

        return [
            text(f"Cleared {len(bans)} ban(s) for '{app_name}'."),
            summary(f"cleared {len(bans)} bans for {app_name}"),
        ]


@register
@dataclass(frozen=True)
class WafReconcileBansCmd(Command):
    """
    Run the ban scorer across all WAF-enabled apps (on demand).

    Reads each app's audit stream, bans repeat offenders for the configured TTL,
    expires elapsed bans, and reloads changed proxies. Safe to run repeatedly.
    The server runs this same cycle in-process on a timer (``waf_bans_service``);
    this command is the manual/debug entry point.
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("waf", "reconcile-bans")

    def call(self, *args):
        from hop3.project.config import (  # ruff:ignore[import-outside-top-level]
            AppConfig,
        )

        apps = AppRepository(session=self.db_session).list_all_ordered()
        active_total = 0
        for app in apps:
            try:
                app_config = AppConfig.from_dir(app.app_path)
            except Exception:  # a missing/broken app dir is skippable
                continue
            active_total += reconcile_bans(app, app_config, self.db_session)
        self.db_session.commit()
        return [
            text(
                f"Reconciled WAF bans across {len(apps)} app(s); "
                f"{active_total} active ban(s)."
            ),
            summary("reconciled waf bans"),
        ]
