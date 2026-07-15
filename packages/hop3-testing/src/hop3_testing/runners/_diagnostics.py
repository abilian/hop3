# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Shared SUT-side failure diagnostics for the test runners.

When a test fails or times out, the *target* holds the answer — the app log, the
nginx/uWSGI config, the journal, the docker state, and the app list
(`hop3 apps`). The deployment runner already collects this; the tutorial and demo
runners historically did not, so a tutorial `hop3 deploy` that timed out was a
black box ("Command timed out after 120s" and nothing else). This module gives
all runners one uniform, never-raising collector.

The `hop3 apps` snapshot is collected *unconditionally* (no app name needed): it
reveals leftover/stranded apps (e.g. one still holding a fixed port) and an app
stuck mid-build at the moment a client-side deploy timeout fired — exactly the
case where the per-app build log doesn't exist yet.
"""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from hop3_testing.bundle import collect_diagnostic_bundle
from hop3_testing.runtime_diagnostics import collect_runtime_logs

if TYPE_CHECKING:
    from hop3_testing.bundle import Bundle
    from hop3_testing.targets.base import DeploymentTarget


def target_kind(target: DeploymentTarget) -> str:
    """Map a target to the bundle's ``target_kind`` ("ssh"/"docker")."""
    return "ssh" if "Remote" in type(target).__name__ else "docker"


def hop3_apps_snapshot(target: DeploymentTarget) -> str:
    """A ``hop3 apps`` listing from the target, or "" if unavailable.

    Name-independent, so it's useful even when the failing app's name is unknown
    (demos) or mis-derived: it surfaces leftover/stranded apps and an app stuck
    in a transitional (building/starting) state when a deploy timed out.
    """
    # `hop3` lives in the hop3 user's venv (/home/hop3/venv/bin), which isn't on
    # root's PATH in the non-login shell exec_run uses — a bare `hop3 apps` then
    # fails with "hop3: command not found". Prepend the venv (and the usual
    # install dirs) so the snapshot actually runs; the trailing $PATH keeps the
    # Docker target working where hop3 is already on PATH.
    cmd = "PATH=/home/hop3/venv/bin:/usr/local/bin:$PATH hop3 apps"
    try:
        _code, out, err = target.exec_run(cmd)
    except Exception:
        out = err = ""
    body = (out or "") + (err or "")

    # The on-target CLI is usually NOT configured to talk to its own server
    # (the deploy ran with HOP3_API_URL/HOP3_API_TOKEN in its env; this probe
    # has neither), so `hop3 apps` prints the multi-line "Hop3 CLI is not
    # configured" setup help — useless and misleading as a diagnostic. Fall back
    # to the filesystem, which is the ground truth for stranded/leftover apps.
    if not body.strip() or "is not configured" in body:
        try:
            _c, ls_out, _e = target.exec_run("ls -1 /home/hop3/apps 2>/dev/null")
        except Exception:
            return ""
        listing = (ls_out or "").strip()
        if not listing:
            return ""
        return "=== apps on target (/home/hop3/apps) ===\n" + listing

    return "=== hop3 apps (target app list) ===\n" + body


def collect_failure_diagnostics(
    target: DeploymentTarget,
    app_name: str | None,
    *,
    deploy_logs: str = "",
    expected_port: int | None = None,
) -> tuple[str, Bundle | None]:
    """SUT-side diagnostics for a failed/timed-out test. Never raises.

    Returns ``(runtime_logs, bundle)``:
    - ``runtime_logs`` always includes the ``hop3 apps`` snapshot, plus this
      app's runtime logs when ``app_name`` is known.
    - ``bundle`` is the unified diagnostic bundle (classifier + headline) when an
      app name is known; ``None`` otherwise.
    """
    sections: list[str] = []

    apps = hop3_apps_snapshot(target)
    if apps:
        sections.append(apps)

    if app_name:
        with suppress(Exception):  # diagnostics must not crash the run
            logs = collect_runtime_logs(target, app_name)
            if logs:
                sections.append(logs)

    bundle: Bundle | None = None
    if app_name:
        with suppress(Exception):
            bundle = collect_diagnostic_bundle(
                target,
                app_name,
                deploy_logs=deploy_logs,
                expected_port=expected_port,
                target_kind=target_kind(target),
            )

    return "\n\n".join(sections), bundle
