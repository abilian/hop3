# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Deploy-time wiring for the Layer-7 WAF (ADR 050).

Three lifecycle hooks, mirroring ``fixed_ports``:

- :func:`configure_waf_preflight` — runs BEFORE the build/deploy. When
  ``[waf].enabled``, it resolves the named networks, compiles the policy, and
  **validates it loads** (compile-before-commit, §5) — aborting the deploy on a
  bad policy — then allocates the proxy's loopback port so nginx (configured
  during deploy) points at the proxy. When WAF is off, it tears down any prior
  WAF state and clears ``waf_port``.
- :func:`start_waf_proxy` — runs AFTER the app is deployed (its ``port`` is
  known): writes/refreshes the LeWAF proxy's uWSGI Emperor vassal so the proxy
  fronts the app.
- :func:`teardown_waf` — on destroy: stops the vassal and removes the rules.

The proxy is an ordinary supervised userspace process (the ``hop3`` user), so it
needs no rootd (ADR 050 "Relationship to hop3-rootd").
"""

from __future__ import annotations

import grp
import json
import os
import pwd
import shlex
import shutil
from contextlib import suppress
from typing import TYPE_CHECKING

from hop3 import config as c
from hop3.core.plugins import get_waf_engine
from hop3.lib import Diagnosis, abort_with_diagnosis, get_free_port, log
from hop3.orm import Ban, BanRepository, NetworkRepository
from hop3.project.schema import validate_hop3_toml
from hop3.waf import WafCompileError
from hop3.waf.bans import parse_duration, sources_to_ban, utcnow

if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path

    from sqlalchemy.orm import Session

    from hop3.orm import App
    from hop3.project.config import AppConfig
    from hop3.project.schema import WafSection


def _waf_section(app_config: AppConfig) -> WafSection | None:
    """The validated ``[waf]`` policy, or None when no WAF is declared."""
    raw = app_config.hop3_config.waf
    if not raw:
        return None
    return validate_hop3_toml({"waf": raw}).waf


def _resolve_networks(db_session: Session | None) -> dict[str, list[str]]:
    """Operator-defined named networks (name -> CIDRs) for gate conditions."""
    if db_session is None:
        return {}
    repo = NetworkRepository(session=db_session)
    return {n.name: list(n.cidrs) for n in repo.get_many()}


def _vassal_name(app_name: str) -> str:
    # `{app}_waf.1.ini` so the app teardown's `{app}*.ini` sweep also reaps it.
    return f"{app_name}_waf.1.ini"


def configure_waf_preflight(
    app: App, app_config: AppConfig, db_session: Session | None
) -> None:
    """Compile + validate the WAF policy and allocate the proxy port (or tear
    down WAF state when disabled). Aborts the deploy loudly on a bad policy."""
    section = _waf_section(app_config)
    if section is None or not section.enabled:
        if app.waf_port:
            _stop_proxy_vassal(app.name)
            with suppress(Exception):
                get_waf_engine().remove_app(app.name)
            app.waf_port = 0
            log(f"WAF disabled for '{app.name}' — proxy torn down", level=2, fg="blue")
        return

    engine = get_waf_engine()
    networks = _resolve_networks(db_session)
    try:
        engine.configure_app(app.name, section, networks)
        engine.validate(app.name)
    except WafCompileError as e:
        abort_with_diagnosis(
            Diagnosis(
                component="WAF",
                action=f"compile the [waf] policy for '{app.name}'",
                reason=str(e),
                hint=(
                    "the WAF is enabled but its policy can't be compiled, so the "
                    "app would deploy unprotected — fix the [waf] section"
                ),
                troubleshooting=[
                    "hop3 network list  # gates reference named networks",
                    "review [waf] allow / [[waf.gate]] / [[waf.tuning]] in hop3.toml",
                ],
            )
        )
    except ImportError:
        abort_with_diagnosis(
            Diagnosis(
                component="WAF",
                action=f"start the WAF for '{app.name}'",
                reason="the LeWAF engine ('waf' extra) is not installed",
                hint="install the WAF extra on the server (needs Python 3.12+)",
                troubleshooting=["pip install 'hop3-server[waf]'"],
            )
        )

    if not app.waf_port:
        app.waf_port = get_free_port()
    log(
        f"WAF enabled for '{app.name}' (mode={section.mode}, proxy port "
        f"{app.waf_port})",
        level=1,
        fg="green",
    )


def start_waf_proxy(app: App, app_config: AppConfig) -> None:
    """(Re)write the LeWAF proxy vassal so it fronts the now-running app."""
    section = _waf_section(app_config)
    if section is None or not section.enabled:
        return
    engine = get_waf_engine()
    upstream = f"http://127.0.0.1:{app.port}"
    cmd = engine.proxy_command(app.name, upstream, app.waf_port)
    _write_proxy_vassal(app.name, cmd)
    log(
        f"WAF proxy for '{app.name}': 127.0.0.1:{app.waf_port} -> {upstream}",
        level=1,
        fg="green",
    )


def teardown_waf(app: App) -> None:
    """On destroy: stop the proxy vassal and remove its rules (best-effort)."""
    _stop_proxy_vassal(app.name)
    with suppress(Exception):
        get_waf_engine().remove_app(app.name)
    app.waf_port = 0


def reconcile_bans(
    app: App,
    app_config: AppConfig,
    db_session: Session | None,
    now: datetime | None = None,
) -> int:
    """Score the WAF audit stream, update the ban DB + denylist, reload the proxy.

    Idempotent and safe to run on a timer: new offenders (over threshold within
    the window, not in an exempt network) are banned for the configured TTL,
    existing bans are refreshed, elapsed bans are dropped, and the proxy's
    denylist file is regenerated from the active set and reloaded. Returns the
    number of active bans. No-op unless ``[waf].enabled`` and ``[waf.bans].enabled``.
    """
    section = _waf_section(app_config)
    if section is None or not section.enabled:
        return 0
    bans_cfg = section.bans
    if bans_cfg is None or not bans_cfg.enabled or db_session is None:
        return 0

    now = now or utcnow()
    engine = get_waf_engine()
    window = parse_duration(bans_cfg.window)
    duration = parse_duration(bans_cfg.duration)
    entries = _read_audit(engine.audit_path(app.name))
    offenders = sources_to_ban(
        entries,
        threshold=bans_cfg.threshold,
        window=window,
        now=now,
        exempt_cidrs=_exempt_cidrs(db_session),
    )

    repo = BanRepository(session=db_session)
    for ip, count in offenders.items():
        existing = repo.get_for_source(app.id, ip)
        if existing is not None:
            existing.expires_at = now + duration  # refresh the TTL
        else:
            db_session.add(
                Ban(
                    app_id=app.id,
                    app_name=app.name,
                    source=ip,
                    reason=f"{count} violations in {bans_cfg.window}",
                    expires_at=now + duration,
                )
            )
    for ban in repo.list_for_app(app.id):
        if ban.expires_at <= now:
            db_session.delete(ban)
    db_session.flush()

    active = sorted(b.source for b in repo.list_active(app.id, now))
    # Reload the proxy only when the denylist actually changed — this runs on a
    # frequent timer (waf_bans_service), so a no-op reload every cycle would
    # needlessly churn every WAF proxy.
    if engine.write_bans(app.name, active):
        reload_proxy(app.name)
    return len(active)


def reload_proxy(app_name: str) -> None:
    """Reload the proxy vassal (Emperor re-reads it on mtime change)."""
    enabled = c.UWSGI_ENABLED / _vassal_name(app_name)
    if enabled.exists():
        enabled.touch()


def _read_audit(path: Path) -> list[dict]:
    """Parse the JSONL audit stream, skipping malformed lines."""
    if not path.exists():
        return []
    entries: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        with suppress(json.JSONDecodeError):
            entries.append(json.loads(line))
    return entries


def _exempt_cidrs(db_session: Session | None) -> list[str]:
    """All operator-named-network CIDRs — the ban exemption list (invariant 5)."""
    cidrs: list[str] = []
    for net_cidrs in _resolve_networks(db_session).values():
        cidrs.extend(net_cidrs)
    return cidrs


def _write_proxy_vassal(app_name: str, cmd: list[str]) -> None:
    """Write the uWSGI Emperor vassal that supervises the LeWAF proxy.

    A bare vassal (no app/socket) whose only job is an ``attach-daemon`` running
    the proxy — the same supervision pattern app workers use, so create/reload
    (file copy bumps mtime) and reap (file removal) come for free from Emperor.
    """
    from hop3.orm import (  # ruff:ignore[import-outside-top-level]
        App,
    )
    from hop3.run.uwsgi.settings import (  # ruff:ignore[import-outside-top-level]
        UwsgiSettings,
    )

    app = App(name=app_name)
    log_file = app.log_path / "waf.1.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    pw_name = pwd.getpwuid(os.getuid()).pw_name
    gr_name = grp.getgrgid(os.getgid()).gr_name
    daemon = _daemon_command(cmd, log_file)

    settings = UwsgiSettings()
    settings += [
        ("master", "true"),
        ("uid", pw_name),
        ("gid", gr_name),
        ("procname-prefix", f"{app_name}:waf:"),
        ("attach-daemon", daemon),
        ("logto2", str(log_file)),
    ]
    available = c.UWSGI_AVAILABLE / _vassal_name(app_name)
    enabled = c.UWSGI_ENABLED / _vassal_name(app_name)
    settings.write(available)
    shutil.copyfile(available, enabled)


def _daemon_command(cmd: list[str], log_file) -> str:
    """The uWSGI ``attach-daemon`` shell string that runs the proxy ``cmd``.

    ``exec`` so the proxy replaces the shell (clean signals / reaping by the
    vassal); args are ``shlex``-quoted; output appends to the app log so failures
    are visible via ``hop3 app logs`` (never discarded).
    """
    joined = " ".join(shlex.quote(a) for a in cmd)
    return f'sh -c "exec {joined} >>{log_file} 2>&1"'


def _stop_proxy_vassal(app_name: str) -> None:
    """Remove the proxy vassal so Emperor stops it (and its attached daemon)."""
    name = _vassal_name(app_name)
    (c.UWSGI_ENABLED / name).unlink(missing_ok=True)
    (c.UWSGI_AVAILABLE / name).unlink(missing_ok=True)
