# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0


"""
nginx ops: reload, validate_config.

These ops retire the existing /etc/sudoers.d/hop3 fragment that grants
the hop3 user NOPASSWD access to four nginx-related commands. Now that
rootd is the kernel-boundary executor, those calls go through the
typed-intent API and can be audited, validated, and policy-controlled
in one place.

See ADR 041 §2 ("Why nginx is in v1") and §12 ("Sudoers fragment retirement").
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from hop3_rootd.exec import CommandTimeoutError, Exec, InvalidBinaryError
from hop3_rootd.ops._base import OpContext, register
from hop3_rootd.protocol import Request

# --- Errors / constants --------------------------------------------------


class NginxBinaryNotFoundError(Exception):
    """Neither systemctl nor nginx is on the allow-list / on this host."""


class NginxReloadNotAppliedError(Exception):
    """
    The reload command returned rc=0 but nginx did not adopt the new config.

    ``nginx -s reload`` / ``systemctl reload nginx`` only *signal* the master;
    nginx then tests the new config asynchronously and, on any failure (a
    syntax error slipping past ``nginx -t``, or a listen/bind conflict with a
    socket a stale config still holds), logs ``[emerg]`` and keeps running the
    OLD config. rc stays 0, so without this check a deploy would report success
    while the app's routes are not live.
    """


# Verification budget: a valid reload forks fresh workers within a second, and
# _reload_applied returns the moment one appears. A REJECTED reload forks none,
# so it runs to this ceiling before failing loud — kept short because the poll
# blocks the single-threaded daemon (server.py) from serving other clients.
_RELOAD_VERIFY_ATTEMPTS = 20
_RELOAD_VERIFY_POLL_S = 0.1
_NGINX_ERROR_LOG = Path("/var/log/nginx/error.log")
_PROC_ROOT = Path("/proc")
_CLK_TCK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100

# Seams (module-level so unit tests can substitute them without real nginx,
# /proc, or wall-clock sleeps).
_sleep = time.sleep


def _ticks_since_boot() -> float | None:
    """
    Now, in clock ticks since boot — the unit of /proc/PID/stat starttime.

    Captured just before a reload so a worker forked *after* it (a real reload)
    is distinguishable from the pre-existing ones by start time alone — no PID
    baseline to miss. Returns None if /proc/uptime is unreadable (non-Linux).
    """
    try:
        uptime_s = float((_PROC_ROOT / "uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return None
    return uptime_s * _CLK_TCK


def _nginx_worker_starttimes() -> list[float]:
    """
    Start time (ticks since boot) of every nginx worker process, via /proc.

    A worker is any process whose title is ``nginx: worker process`` (nginx sets
    it with setproctitle; /proc/PID/cmdline reflects it, NUL- or space-joined).
    """
    starttimes: list[float] = []
    try:
        entries = list(_PROC_ROOT.iterdir())
    except OSError:
        return starttimes  # no /proc (non-Linux / unreadable)
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes()
            if b"nginx: worker process" not in cmdline.replace(b"\x00", b" "):
                continue
            stat = (entry / "stat").read_text()
        except OSError:
            continue  # the process exited between listing and reading
        # /proc/PID/stat: "pid (comm) state ppid ... starttime(field 22) ...".
        # comm can contain spaces/parens, so parse fields after the last ')'.
        after_comm = stat[stat.rfind(")") + 1 :].split()
        try:
            starttimes.append(float(after_comm[19]))  # field 22 → index 19
        except (IndexError, ValueError):
            continue
    return starttimes


def _reload_applied(since_ticks: float | None) -> bool:
    """
    True once an nginx worker forked at/after ``since_ticks`` (a real reload).

    Uses worker START TIME, not a PID-set diff: a transient /proc enumeration
    miss can't make an old worker look new, so it can't report a rejected reload
    as applied. When ``since_ticks`` is None (no /proc uptime) the check is
    inconclusive rather than falsely positive — the caller fails loud.
    """
    if since_ticks is None:
        return False
    for _ in range(_RELOAD_VERIFY_ATTEMPTS):
        if any(st >= since_ticks for st in _nginx_worker_starttimes()):
            return True
        _sleep(_RELOAD_VERIFY_POLL_S)
    return False


def _last_reload_error(since_offset: int) -> str | None:
    """
    The last ``[emerg]``/``[alert]`` line nginx logged *during this reload*.

    Reads only the bytes appended to the error log since ``since_offset`` (the
    log size captured before the reload), so a stale error from an unrelated
    earlier incident is never misattributed as this reload's cause. Best-effort:
    returns None if the log is unreadable or logs elsewhere (custom error_log /
    syslog), leaving the caller to fall back to a generic hint.
    """
    try:
        with _NGINX_ERROR_LOG.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            if size < since_offset:  # rotated/truncated mid-reload — can't scope
                return None
            fh.seek(since_offset)
            fresh = fh.read()
    except OSError:
        return None
    for line in reversed(fresh.decode("utf-8", "replace").splitlines()):
        if "[emerg]" in line or "[alert]" in line:
            return line.strip()
    return None


def _error_log_size() -> int:
    """Current size of nginx's error log (0 if absent), to scope error scanning."""
    try:
        return _NGINX_ERROR_LOG.stat().st_size
    except OSError:
        return 0


# Reload methods, in preferred order. We try them sequentially until one
# succeeds. Mirrors the existing fallback chain in the proxy plugin.
def _reload_methods(exec: Exec) -> list[tuple[list[str], str]]:
    """
    Construct the ordered list of reload commands to try, given the
    binaries actually present on this host. Each entry is (argv, label).
    """
    methods: list[tuple[list[str], str]] = []
    systemctl = exec.resolve("systemctl")
    if systemctl is not None:
        methods.append(([systemctl, "reload", "nginx"], "systemctl"))
    nginx = exec.resolve("nginx")
    if nginx is not None:
        methods.append(([nginx, "-s", "reload"], "nginx -s reload"))
    return methods


# --- nginx.reload --------------------------------------------------------


@register("nginx.reload")
def reload_nginx(_req: Request, ctx: OpContext) -> dict[str, Any]:
    """
    Reload nginx config without dropping connections.

    Tries systemctl first, then `nginx -s reload`. Reports which method
    succeeded for diagnostics.

    A ``rc == 0`` from the reload command only means nginx *accepted the
    signal* — it tests the new config asynchronously and silently keeps the old
    one on failure. So this confirms the reload actually applied (nginx spawned
    fresh workers) before reporting success; otherwise a broken deploy — e.g. a
    leftover conf whose listen conflicts with a held socket, which blocks every
    reload — would look successful while no new route goes live.

    Returns:
        {"method": "systemctl" | "nginx -s reload"}

    Raises:
        NginxBinaryNotFoundError: no working reload method is available.
        NginxReloadNotAppliedError: a method returned rc=0 but nginx did not
            adopt the new config.
    """
    methods = _reload_methods(ctx.exec)
    if not methods:
        raise NginxBinaryNotFoundError(
            "no nginx-reload method available "
            "(neither systemctl nor nginx found on the allow-list)"
        )

    # Markers captured BEFORE the reload so verification is scoped to it: a
    # worker forked after `since_ticks` is this reload's; error-log bytes past
    # `log_offset` are this reload's.
    since_ticks = _ticks_since_boot()
    log_offset = _error_log_size()

    last_error: str | None = None
    for argv, label in methods:
        try:
            result = ctx.exec.run(argv, timeout=10.0)
        except InvalidBinaryError as e:
            last_error = str(e)
            continue
        except CommandTimeoutError as e:
            # A wedged systemd shouldn't strand the deploy — the next method
            # (`nginx -s reload`) signals the master directly and may still work.
            last_error = str(e)
            continue
        if result.success:
            if _reload_applied(since_ticks):
                return {"method": label}
            # rc=0 but the config was rejected at reload time. Retrying another
            # method would hit the same rejection (it's the config, not the
            # method), so fail loud with nginx's own reason.
            reason = _last_reload_error(log_offset) or (
                "no fresh worker processes appeared, so nginx kept the previous "
                "config (run `nginx -t` and check /var/log/nginx/error.log)"
            )
            raise NginxReloadNotAppliedError(
                f"nginx accepted the reload (via {label}) but did not apply the "
                f"new config: {reason}"
            )
        last_error = (
            f"{label} returned rc={result.returncode}; stderr={result.stderr.strip()}"
        )

    # All methods failed.
    raise NginxBinaryNotFoundError(
        f"all nginx-reload methods failed; last error: {last_error}"
    )


# --- nginx.validate_config ------------------------------------------------


@register("nginx.validate_config", audit=False)
def validate_config(_req: Request, ctx: OpContext) -> dict[str, Any]:
    """
    Run `nginx -t` to validate the current nginx config files.

    Pure read — doesn't reload anything. nginx -t exits non-zero on
    config errors, so rc != 0 isn't a kernel_error — it's a structured
    {valid: False, errors: [...]} result.
    """
    nginx = ctx.exec.resolve("nginx")
    if nginx is None:
        raise NginxBinaryNotFoundError(
            "nginx not on allow-list (not found on PATH or not whitelisted)"
        )

    try:
        result = ctx.exec.run([nginx, "-t"], timeout=10.0)
    except InvalidBinaryError as e:
        raise NginxBinaryNotFoundError(str(e)) from e

    if result.success:
        return {"valid": True}

    # nginx -t writes diagnostics to stderr. Parse out the error lines.
    errors = _parse_nginx_t_errors(result.stderr)
    return {"valid": False, "errors": errors, "raw_stderr": result.stderr}


def _parse_nginx_t_errors(stderr: str) -> list[str]:
    """
    Pull error / warning lines from nginx -t stderr.

    nginx -t output:
        nginx: [emerg] unexpected "}" in /etc/nginx/...:42
        nginx: configuration file /etc/nginx/nginx.conf test failed

    We return only the meaningful error lines (containing [emerg] /
    [error] / [warn] / similar markers, or the "test failed" verdict).
    """
    if not stderr:
        return []
    out: list[str] = []
    for raw in stderr.splitlines():
        line = raw.strip()
        if not line:
            continue
        if any(
            marker in line for marker in ("[emerg]", "[error]", "[warn]", "test failed")
        ):
            out.append(line)
    return out or [stderr.strip()]
