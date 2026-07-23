# Copyright (c) 2023-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
`hop3 system` commands.

Four subcommands by design:

- ``system status`` — "Is the server OK?". Full health report + identity
  header at top. Honours ``--quiet`` and ``--json``.
- ``system info``   — "What is this server?". Facts only (version, host,
  IPs, uptime). With ``-v``, lists loaded plugins.
- ``system logs``   — server logs.
- ``system cleanup`` — Docker resource cleanup.

The pre-0.5 surface had ``check`` / ``status`` / ``uptime`` / ``ps`` as
separate commands; they were collapsed (uptime → identity header) or
removed (``ps aux`` of the host was a security smell). See the plan at
``local-notes/plans/17-system-commands-redesign.md``.
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import pathlib
import platform
import pwd
import re
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, ClassVar

from hop3.config import HOP3_ROOT, config
from hop3.core.plugins import get_plugin_manager
from hop3.lib.args import parse_cli_args
from hop3.lib.logging import DEFAULT_LOG_FILE
from hop3.lib.registry import register
from hop3.plugins.redis.redis import REDIS_PASS_FILE
from hop3.plugins.s3.backend import HOP3_S3_ENV_FILE
from hop3.server.health import get_all_health_checks, run_health_check

from ._base import Command, NamespaceCommand
from ._response import data, error, success, text, warning

if TYPE_CHECKING:
    from hop3.core.protocols import Severity


#
# -- Helpers ------------------------------------------------------------------
#

_SEVERITY_ICON: dict[Severity, str] = {"ok": "✓", "warn": "⚠", "fail": "✗"}
_SEVERITY_RANK: dict[Severity, int] = {"ok": 0, "warn": 1, "fail": 2}


def _worst(severities: list[Severity]) -> Severity:
    """Return the most severe entry; defaults to ok if list is empty."""
    if not severities:
        return "ok"
    return max(severities, key=lambda s: _SEVERITY_RANK[s])


@dataclass(frozen=True)
class CheckItem:
    """One row inside a ``StatusCmd`` section."""

    name: str
    severity: Severity
    detail: str = ""


@dataclass(frozen=True)
class CheckSection:
    """One titled group of related checks."""

    title: str
    items: list[CheckItem] = field(default_factory=list)


def _resolved_ips() -> list[str]:
    """Best-effort getaddrinfo for the host's own name."""
    ips: list[str] = []
    try:
        addr_info = socket.getaddrinfo(socket.gethostname(), None, socket.AF_UNSPEC)
    except socket.gaierror:
        return ips
    for item in addr_info:
        ip = str(item[4][0])
        if (
            not ip.startswith("127.")
            and not ip.startswith("::1")
            and not ip.startswith("fe80")
            and ip not in ips
        ):
            ips.append(ip)
    return ips


def _probed_ip() -> str | None:
    """
    Fallback when getaddrinfo gives nothing: ask the kernel which IP it
    would use to reach a public address. No traffic is actually sent.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return None


def _get_ip_addresses() -> list[str]:
    """Non-loopback IP addresses of this host."""
    ips = _resolved_ips()
    if not ips:
        probed = _probed_ip()
        if probed:
            ips.append(probed)
    return ips


def _format_duration(seconds: float) -> str:
    """'14d 3h' for ≥1 day, else '3h 7m'."""
    days, rem = divmod(int(seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}d {hours}h"
    return f"{hours}h {minutes}m"


def _get_uptime() -> str | None:
    """Human-readable host uptime (e.g. '14d 3h'). Linux-only."""
    try:
        seconds = float(pathlib.Path("/proc/uptime").read_text().split()[0])
    except (FileNotFoundError, ValueError, OSError):
        return None
    return _format_duration(seconds)


def _process_uptime() -> str | None:
    """
    Uptime of THIS hop3-server process (e.g. '2d 3h'). Linux-only.

    Derived from ``/proc/self/stat`` (process start, in clock ticks since boot)
    and ``/proc/uptime`` (seconds since boot) — no psutil dependency. This is
    the *server* uptime, distinct from host uptime: it resets on every
    hop3-server restart.
    """
    try:
        clk_tck = os.sysconf("SC_CLK_TCK")
        stat = pathlib.Path("/proc/self/stat").read_text()
        # comm (2nd field) can contain spaces/parens; everything after the final
        # ')' is state(3), …, so starttime (field 22) is index 19 of that tail.
        after_comm = stat[stat.rindex(")") + 1 :].split()
        start_ticks = float(after_comm[19])
        boot_uptime = float(pathlib.Path("/proc/uptime").read_text().split()[0])
        return _format_duration(boot_uptime - start_ticks / clk_tck)
    except (OSError, ValueError, IndexError, ZeroDivisionError):
        return None


def _acme_engine_summary() -> str:
    """
    The TLS issuance engine actually in effect on the running server.

    Reads the live config singleton (not the file), so it reflects what the
    process will use — the answer to "why is my cert self-signed?".
    """
    engine = config.ACME_ENGINE
    if engine == "certbot":
        email = config.ACME_EMAIL
        return f"certbot ({email})" if email else "certbot (ACME_EMAIL not set!)"
    return engine


def _database_backend() -> str:
    """
    Control-plane DB backend (scheme only — never the URI, which may carry
    a password). Mirrors the resolution in ``orm.session.get_session_factory``.
    """
    uri = os.environ.get("HOP3_DATABASE_URI", "") or f"sqlite:///{HOP3_ROOT}/hop3.db"
    return uri.split(":", 1)[0] or "unknown"


def _installed_features() -> list[str]:
    """
    Optional backing services / build features provisioned on this server.

    Detected from the installer's own footprint, not a registry of *available*
    plugins: addon admin creds in ``hop3-server.toml`` (postgres/mysql), the
    per-service secret files the installer writes under ``/etc/hop3`` (redis/s3),
    and the ``nix`` binary on PATH.
    """
    features: list[str] = []
    try:
        content = (HOP3_ROOT / "hop3-server.toml").read_text(encoding="utf-8")
    except OSError:
        content = ""
    if "POSTGRES_SUPERUSER_PASSWORD" in content:
        features.append("postgres")
    if "MYSQL_SUPERUSER_PASSWORD" in content:
        features.append("mysql")

    # The per-service secrets are the installer's marker for `--with redis|s3`.
    if pathlib.Path(REDIS_PASS_FILE).exists():
        features.append("redis")
    if pathlib.Path(HOP3_S3_ENV_FILE).exists():
        features.append("s3")
    if shutil.which("nix"):
        features.append("nix")
    return features


def _docker_installed() -> bool:
    """Cheap fact check: is the docker CLI on PATH? No subprocess invocation."""
    return shutil.which("docker") is not None


def _read_build_info() -> dict | None:
    """
    Read the deploy-provenance manifest written by hop3-deploy/-install.

    Returns the parsed dict, or None when the file is absent or unreadable
    (e.g. an install that predates build-info, or a hand-rolled deploy).
    """
    try:
        raw = (HOP3_ROOT / "build-info.json").read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _commit_from_direct_url() -> tuple[str | None, str | None]:
    """
    Fallback provenance: read the commit pip recorded for a git install.

    PEP 610 writes ``direct_url.json`` into the dist-info for ``pip install
    git+...`` deploys. Returns ``(commit, requested_revision)`` — both None
    for PyPI/local installs (which carry no VCS info).
    """
    try:
        raw = importlib.metadata.distribution("hop3_server").read_text(
            "direct_url.json"
        )
    except (importlib.metadata.PackageNotFoundError, OSError):
        return None, None
    if not raw:
        return None, None
    try:
        vcs = json.loads(raw).get("vcs_info", {})
    except ValueError:
        return None, None
    return vcs.get("commit_id"), vcs.get("requested_revision")


def _provenance_lines() -> list[str]:
    """
    Build the Commit / Branch / Deploy method / Deployed display lines.

    Prefers the deploy manifest; falls back to pip's recorded git commit;
    shows ``unknown`` when neither is available (so the field is never silently
    missing — its absence is itself diagnostic).
    """
    info = _read_build_info() or {}
    commit = info.get("git_commit")
    branch = info.get("git_branch")
    dirty = info.get("git_dirty")
    method = info.get("deploy_method")
    deployed_at = info.get("deployed_at")

    if not commit:
        du_commit, du_branch = _commit_from_direct_url()
        commit = du_commit
        branch = branch or du_branch

    commit_str = commit or "unknown"
    if dirty:
        commit_str += " (dirty)"

    lines = [f"Commit:         {commit_str}"]
    if branch:
        lines.append(f"Branch:         {branch}")
    if method:
        lines.append(f"Deploy method:  {method}")
    if deployed_at:
        lines.append(f"Deployed:       {deployed_at}")
    return lines


#
# -- The 'system' group ------------------------------------------------------
#


@register
class SystemCmd(NamespaceCommand):
    """
    Manage the hop3 system.

    Examples:
        hop3 system status             # Full health report
        hop3 system info               # Facts about this server
        hop3 system logs               # Server logs
        hop3 system cleanup            # Reclaim Docker resources
    """

    name: ClassVar[tuple[str, ...]] = ("system",)


#
# -- system status (the rich health view) -------------------------------------
#


@register
class StatusCmd(Command):
    """
    Show the server's health — services, addons, disk, certs (vs 'system info', static facts).

    Default output: one-line identity header + per-section health table.
    Bottom line summarises warnings and failures.

    Options:
        --quiet, -q   One-line summary only (suitable for scripting).
        --json        Machine-readable JSON output.

    Exit code is non-zero when there is any warning or failure.

    Examples:
        hop3 system status
        hop3 system status --quiet
        hop3 system status --json
    """

    name: ClassVar[tuple[str, ...]] = ("system", "status")

    def call(self, *args: str, **kwargs: object) -> list[dict]:
        quiet = "--quiet" in args or "-q" in args
        json_mode = "--json" in args

        identity = self._gather_identity()
        sections = [
            self._check_services(),
            self._check_addons(),
            self._check_filesystem(),
            self._check_configuration(),
            self._check_certificates(),
            self._check_disk(),
        ]
        overall = _worst([
            item.severity for section in sections for item in section.items
        ])

        if json_mode:
            return [data(self._to_json(identity, sections, overall))]
        if quiet:
            return [self._render_quiet(overall, sections)]
        return self._render_rich(identity, sections, overall)

    # -- gathering --

    def _gather_identity(self) -> dict[str, str]:
        version = importlib.metadata.version("hop3_server")
        hostname = socket.gethostname()
        ips = _get_ip_addresses()
        uptime = _get_uptime()
        return {
            "hostname": hostname,
            "ip": ips[0] if ips else "unknown",
            "version": version,
            "uptime": uptime or "unknown",
        }

    def _check_services(self) -> CheckSection:
        services = [
            ("hop3-server", "Hop3 Server"),
            ("nginx", "Nginx"),
            ("uwsgi-hop3", "uWSGI Emperor"),
        ]
        items: list[CheckItem] = []
        for unit, label in services:
            result = subprocess.run(
                ["systemctl", "is-active", unit],
                capture_output=True,
                text=True,
                check=False,
            )
            active = result.stdout.strip() == "active"
            items.append(
                CheckItem(
                    name=label,
                    severity="ok" if active else "fail",
                    detail="running" if active else "not running",
                )
            )
        return CheckSection(title="Services", items=items)

    def _check_addons(self) -> CheckSection:
        items: list[CheckItem] = []
        for hc in get_all_health_checks():
            result = run_health_check(hc)
            severity = result.derived_severity
            detail = result.message
            if severity == "ok":
                detail = "ok"
            items.append(CheckItem(name=result.name, severity=severity, detail=detail))
        if not items:
            items.append(
                CheckItem(
                    name="(no addons)",
                    severity="ok",
                    detail="no health checks registered",
                )
            )
        return CheckSection(title="Backing services", items=items)

    def _check_filesystem(self) -> CheckSection:
        required = [
            (HOP3_ROOT, "HOP3_ROOT"),
            (HOP3_ROOT / "apps", "Apps directory"),
            (HOP3_ROOT / "nginx", "Nginx config"),
            (HOP3_ROOT / "uwsgi-available", "uWSGI available"),
            (HOP3_ROOT / "uwsgi-enabled", "uWSGI enabled"),
        ]
        items: list[CheckItem] = []
        for path, label in required:
            if not path.exists():
                items.append(
                    CheckItem(name=label, severity="fail", detail=f"missing ({path})")
                )
            elif not os.access(path, os.W_OK):
                items.append(
                    CheckItem(name=label, severity="fail", detail="not writable")
                )
            else:
                items.append(CheckItem(name=label, severity="ok", detail="writable"))
        try:
            pwd.getpwnam("hop3")
            items.append(CheckItem(name="hop3 user", severity="ok", detail="exists"))
        except KeyError:
            items.append(
                CheckItem(name="hop3 user", severity="fail", detail="not found")
            )
        return CheckSection(title="Filesystem", items=items)

    def _check_configuration(self) -> CheckSection:
        config_file = HOP3_ROOT / "hop3-server.toml"
        items: list[CheckItem] = []
        if not config_file.exists():
            items.append(
                CheckItem(
                    name="Config file",
                    severity="fail",
                    detail=f"missing ({config_file})",
                )
            )
            return CheckSection(title="Configuration", items=items)

        items.append(
            CheckItem(name="Config file", severity="ok", detail=str(config_file))
        )
        try:
            content = config_file.read_text()
        except OSError as e:
            items.append(
                CheckItem(
                    name="Config file", severity="fail", detail=f"read error: {e}"
                )
            )
            return CheckSection(title="Configuration", items=items)

        if "HOP3_SECRET_KEY" in content:
            items.append(
                CheckItem(name="HOP3_SECRET_KEY", severity="ok", detail="configured")
            )
        else:
            items.append(
                CheckItem(
                    name="HOP3_SECRET_KEY",
                    severity="fail",
                    detail="missing (required for auth)",
                )
            )
        return CheckSection(title="Configuration", items=items)

    def _check_certificates(self) -> CheckSection:
        ssl_cert = HOP3_ROOT / "nginx" / "ssl" / "hop3.crt"
        ssl_key = HOP3_ROOT / "nginx" / "ssl" / "hop3.key"
        if ssl_cert.exists() and ssl_key.exists():
            item = CheckItem(name="SSL", severity="ok", detail="configured")
        else:
            item = CheckItem(
                name="SSL",
                severity="warn",
                detail="self-signed (Let's Encrypt not configured)",
            )
        return CheckSection(title="Certificates", items=[item])

    def _check_disk(self) -> CheckSection:
        try:
            usage = shutil.disk_usage(HOP3_ROOT)
        except OSError as e:
            return CheckSection(
                title="Disk",
                items=[CheckItem(name="Disk usage", severity="fail", detail=str(e))],
            )
        percent = (usage.used / usage.total) * 100
        if percent > 90:
            severity: Severity = "fail"
        elif percent > 80:
            severity = "warn"
        else:
            severity = "ok"
        return CheckSection(
            title="Disk",
            items=[
                CheckItem(
                    name="Disk usage", severity=severity, detail=f"{percent:.0f}%"
                )
            ],
        )

    # -- rendering --

    def _render_rich(
        self,
        identity: dict[str, str],
        sections: list[CheckSection],
        overall: Severity,
    ) -> list[dict]:
        lines: list[str] = []
        lines.append(
            f"Hop3 server: {identity['hostname']} ({identity['ip']}) — "
            f"v{identity['version']} — up {identity['uptime']}"
        )

        for section in sections:
            lines.append("")
            lines.append(section.title)
            width = max((len(item.name) for item in section.items), default=0)
            for item in section.items:
                icon = _SEVERITY_ICON[item.severity]
                lines.append(f"  {item.name:<{width}}  {icon} {item.detail}")

        lines.append("")
        summary_text = self._summary_line(overall, sections)
        # Match the bottom-line summary to the worst severity, so the CLI
        # can map error()/warning() to a useful exit code without parsing.
        result: list[dict] = [text("\n".join(lines))]
        if overall == "fail":
            result.append(error(summary_text))
        elif overall == "warn":
            result.append(warning(summary_text))
        else:
            result.append(success(summary_text))
        return result

    def _render_quiet(self, overall: Severity, sections: list[CheckSection]) -> dict:
        if overall == "ok":
            return success("OK")
        non_ok = [
            f"{item.name.lower()} {item.detail}".strip()
            for section in sections
            for item in section.items
            if item.severity != "ok"
        ]
        label = "DEGRADED" if overall == "warn" else "FAILED"
        msg = f"{label}: " + "; ".join(non_ok) if non_ok else label
        return error(msg) if overall == "fail" else warning(msg)

    def _summary_line(self, overall: Severity, sections: list[CheckSection]) -> str:
        warns = sum(1 for s in sections for i in s.items if i.severity == "warn")
        fails = sum(1 for s in sections for i in s.items if i.severity == "fail")
        if overall == "ok":
            return "Status: ✓ all OK"
        parts = []
        if fails:
            parts.append(f"{fails} failure{'s' if fails != 1 else ''}")
        if warns:
            parts.append(f"{warns} warning{'s' if warns != 1 else ''}")
        icon = _SEVERITY_ICON[overall]
        return f"Status: {icon} " + ", ".join(parts)

    def _to_json(
        self,
        identity: dict[str, str],
        sections: list[CheckSection],
        overall: Severity,
    ) -> dict:
        return {
            "identity": identity,
            "overall": overall,
            "sections": [
                {
                    "title": s.title,
                    "items": [
                        {"name": i.name, "severity": i.severity, "detail": i.detail}
                        for i in s.items
                    ],
                }
                for s in sections
            ],
        }


#
# -- system info (facts only, no liveness probes) -----------------------------
#


@register
class InfoCmd(Command):
    """
    Show static facts about this server — version, host, uptime, features (vs 'system status', live health).

    Reports version/provenance, host and *server-process* uptime, the
    control-plane database backend, the TLS issuance engine in effect, and the
    optional backing services installed (postgres/mysql/redis/s3/nix).

    No liveness probes — use ``hop3 system status`` for "is everything OK?".

    Options:
        --verbose, -v   Also list loaded plugins and key paths.

    Examples:
        hop3 system info
        hop3 system info -v
    """

    name: ClassVar[tuple[str, ...]] = ("system", "info")

    def call(self, *args: str, **kwargs: object) -> list[dict]:
        verbose = "--verbose" in args or "-v" in args

        version = importlib.metadata.version("hop3_server")
        python_version = sys.version.split()[0]
        os_info = f"{platform.system()} {platform.release()}"
        hostname = socket.gethostname()
        ips = _get_ip_addresses()
        host_uptime = _get_uptime() or "unknown"
        server_uptime = _process_uptime() or "unknown"
        docker = "installed" if _docker_installed() else "not installed"
        features = _installed_features()

        lines = [
            f"Version:        {version}",
            *_provenance_lines(),
            f"Python:         {python_version}",
            f"Platform:       {os_info}",
            f"Hostname:       {hostname}",
            f"IP Addresses:   {', '.join(ips) if ips else 'unknown'}",
            f"Host uptime:    {host_uptime}",
            f"Server uptime:  {server_uptime}",
            f"Database:       {_database_backend()}",
            f"TLS engine:     {_acme_engine_summary()}",
            f"Docker:         {docker}",
            f"Features:       {', '.join(features) if features else '(none)'}",
        ]

        if verbose:
            lines.extend(self._verbose_info())

        return [text("\n".join(lines))]

    def _verbose_info(self) -> list[str]:
        lines = ["", "Loaded plugins"]
        pm = get_plugin_manager()

        def _collect(hook_name: str) -> list:
            classes: list = []
            for sublist in getattr(pm.hook, hook_name)():
                classes.extend(sublist)
            return classes

        for label, hook in (
            ("Builders", "get_builders"),
            ("Deployers", "get_deployers"),
            ("Toolchains", "get_language_toolchains"),
        ):
            classes = _collect(hook)
            if classes:
                lines.append(f"  {label}:")
                for cls in classes:
                    name = getattr(cls, "name", cls.__name__)
                    if name != cls.__name__:
                        lines.append(f"    - {cls.__name__} ({name})")
                    else:
                        lines.append(f"    - {cls.__name__}")
            else:
                lines.append(f"  {label}: (none loaded)")

        lines.extend([
            "",
            "Paths",
            f"  HOP3_ROOT:    {HOP3_ROOT}",
            f"  Apps dir:     {HOP3_ROOT / 'apps'}",
            f"  Nginx conf:   {HOP3_ROOT / 'nginx'}",
        ])
        return lines


#
# -- system logs --------------------------------------------------------------
#


@register
class SystemLogsCmd(Command):
    """
    Show Hop3 server logs.

    Options:
        -n, --lines N      Number of lines to show (default: 100)
        --since DURATION   Show logs since duration (e.g., 1h, 30m, 1d)
        --level LEVEL      Filter by log level (DEBUG, INFO, WARNING, ERROR)
        --grep PATTERN     Filter lines matching pattern

    Examples:
        hop3 system logs                    # Last 100 lines
        hop3 system logs -n 50              # Last 50 lines
        hop3 system logs --since 1h         # Last hour
        hop3 system logs --level ERROR      # Errors only
        hop3 system logs --grep deploy      # Lines containing 'deploy'
    """

    name: ClassVar[tuple[str, ...]] = ("system", "logs")
    _arg_spec: ClassVar[dict] = {
        "lines": {"short": "-n", "type": int, "default": 100},
        "since": {"type": str, "default": ""},
        "level": {"type": str, "default": ""},
        "grep": {"type": str, "default": ""},
    }

    def call(self, *args: str, **kwargs: object) -> list[dict]:
        parsed = parse_cli_args(args, self._arg_spec)
        lines = parsed["lines"]
        since = parsed["since"] or None
        level = parsed["level"].upper()
        grep = parsed["grep"]

        if not DEFAULT_LOG_FILE.exists():
            return [text(f"No log file found at {DEFAULT_LOG_FILE}")]

        with pathlib.Path(DEFAULT_LOG_FILE).open(encoding="utf-8") as f:
            all_lines = f.readlines()

        if since:
            cutoff = self._parse_since(since)
            if cutoff:
                all_lines = self._filter_by_time(all_lines, cutoff)

        if level:
            all_lines = [ln for ln in all_lines if f"[{level}]" in ln]

        if grep:
            # Case-insensitive substring match (audit M3): compiling the
            # attacker-supplied string as a regex allowed catastrophic
            # backtracking (ReDoS) that exhausts the shared server CPU. Plain
            # substring matches the documented behavior ("lines containing …")
            # and the adjacent --level filter — no regex engine, no ReDoS.
            needle = grep.lower()
            all_lines = [ln for ln in all_lines if needle in ln.lower()]

        result_lines = all_lines[-lines:]

        if not result_lines:
            return [text("No log entries found matching criteria.")]

        return [text("".join(result_lines))]

    def _parse_since(self, since: str) -> datetime | None:
        match = re.match(r"^(\d+)([smhd])$", since.lower())
        if not match:
            return None
        value = int(match.group(1))
        unit = match.group(2)
        delta = {
            "s": timedelta(seconds=value),
            "m": timedelta(minutes=value),
            "h": timedelta(hours=value),
            "d": timedelta(days=value),
        }.get(unit)
        if delta:
            return datetime.now(tz=timezone.utc) - delta
        return None

    def _filter_by_time(self, lines: list[str], cutoff: datetime) -> list[str]:
        result: list[str] = []
        for line in lines:
            if len(line) >= 19:
                try:
                    timestamp = datetime.strptime(
                        line[:19], "%Y-%m-%d %H:%M:%S"
                    ).replace(tzinfo=timezone.utc)
                    if timestamp >= cutoff:
                        result.append(line)
                except ValueError:
                    if result:
                        result.append(line)
        return result


#
# -- system cleanup (Docker resources) ----------------------------------------
#


@register
class CleanupCmd(Command):
    """
    Clean up unused Docker resources (networks, images, containers, volumes).

    Options:
        --dry-run       Show what would be cleaned without doing it
        --all           Also remove unused images (not just dangling ones)
        --volumes       Also prune unused volumes (data loss warning!)

    Removes by default: stopped containers, unused networks, dangling
    images, build cache. With --all also unused images; with --volumes
    also unused volumes (may cause data loss).

    Examples:
        hop3 system cleanup                # Safe cleanup
        hop3 system cleanup --dry-run      # Preview
        hop3 system cleanup --all          # Include unused images
        hop3 system cleanup --volumes      # Include volumes (careful!)
    """

    name: ClassVar[tuple[str, ...]] = ("system", "cleanup")

    def call(self, *args: str, **kwargs: object) -> list[dict]:
        dry_run = "--dry-run" in args
        include_all = "--all" in args
        include_volumes = "--volumes" in args

        results: list[str] = []
        if dry_run:
            results.append("=== DRY RUN - No changes will be made ===\n")

        results.append(self._cleanup_networks(dry_run))
        results.append(self._cleanup_containers(dry_run))
        results.append(self._cleanup_images(dry_run, include_all))
        if include_volumes:
            results.append(self._cleanup_volumes(dry_run))
        results.append(self._cleanup_build_cache(dry_run))

        return [text("\n".join(results))]

    def _cleanup_networks(self, dry_run: bool) -> str:
        lines = ["Docker Networks:"]
        if dry_run:
            result = subprocess.run(
                ["docker", "network", "ls", "--filter", "dangling=true", "-q"],
                capture_output=True,
                text=True,
                check=False,
            )
            ids = [n for n in result.stdout.strip().split("\n") if n]
            lines.append(
                f"  Would remove {len(ids)} unused network(s)"
                if ids
                else "  No unused networks to remove"
            )
        else:
            result = subprocess.run(
                ["docker", "network", "prune", "-f"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                output = result.stdout.strip()
                lines.append(
                    f"  {output}"
                    if "Deleted Networks:" in output
                    else "  No unused networks removed"
                )
            else:
                lines.append(f"  Error: {result.stderr.strip()}")
        return "\n".join(lines)

    def _cleanup_containers(self, dry_run: bool) -> str:
        lines = ["Docker Containers:"]
        if dry_run:
            result = subprocess.run(
                ["docker", "ps", "-aq", "--filter", "status=exited"],
                capture_output=True,
                text=True,
                check=False,
            )
            ids = [c for c in result.stdout.strip().split("\n") if c]
            lines.append(
                f"  Would remove {len(ids)} stopped container(s)"
                if ids
                else "  No stopped containers to remove"
            )
        else:
            result = subprocess.run(
                ["docker", "container", "prune", "-f"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                lines.append(
                    "  Cleaned up stopped containers"
                    if result.stdout.strip()
                    else "  No stopped containers removed"
                )
            else:
                lines.append(f"  Error: {result.stderr.strip()}")
        return "\n".join(lines)

    def _cleanup_images(self, dry_run: bool, include_all: bool) -> str:
        lines = ["Docker Images:"]
        prune_args = ["docker", "image", "prune", "-f"]
        if include_all:
            prune_args.append("-a")

        if dry_run:
            result = subprocess.run(
                ["docker", "images", "-q", "--filter", "dangling=true"],
                capture_output=True,
                text=True,
                check=False,
            )
            ids = [i for i in result.stdout.strip().split("\n") if i]
            if include_all:
                lines.append("  Would remove dangling images + all unused images")
            elif ids:
                lines.append(f"  Would remove {len(ids)} dangling image(s)")
            else:
                lines.append("  No dangling images to remove")
        else:
            result = subprocess.run(
                prune_args, capture_output=True, text=True, check=False
            )
            if result.returncode == 0:
                output = result.stdout.strip()
                if "Total reclaimed space" in output:
                    for line in output.split("\n"):
                        if "Total reclaimed space" in line:
                            lines.append(f"  {line}")
                            break
                else:
                    lines.append("  No images removed")
            else:
                lines.append(f"  Error: {result.stderr.strip()}")
        return "\n".join(lines)

    def _cleanup_volumes(self, dry_run: bool) -> str:
        lines = ["Docker Volumes (WARNING: may cause data loss!):"]
        if dry_run:
            result = subprocess.run(
                ["docker", "volume", "ls", "-q", "--filter", "dangling=true"],
                capture_output=True,
                text=True,
                check=False,
            )
            ids = [v for v in result.stdout.strip().split("\n") if v]
            lines.append(
                f"  Would remove {len(ids)} unused volume(s)"
                if ids
                else "  No unused volumes to remove"
            )
        else:
            result = subprocess.run(
                ["docker", "volume", "prune", "-f"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                output = result.stdout.strip()
                if "Total reclaimed space" in output:
                    for line in output.split("\n"):
                        if "Total reclaimed space" in line:
                            lines.append(f"  {line}")
                            break
                else:
                    lines.append("  No volumes removed")
            else:
                lines.append(f"  Error: {result.stderr.strip()}")
        return "\n".join(lines)

    def _cleanup_build_cache(self, dry_run: bool) -> str:
        lines = ["Docker Build Cache:"]
        if dry_run:
            result = subprocess.run(
                ["docker", "builder", "du"],
                capture_output=True,
                text=True,
                check=False,
            )
            lines.append(
                "  Would clear build cache"
                if result.returncode == 0
                else "  Build cache info unavailable"
            )
        else:
            result = subprocess.run(
                ["docker", "builder", "prune", "-f"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                output = result.stdout.strip()
                if "Total reclaimed space" in output:
                    for line in output.split("\n"):
                        if "Total reclaimed space" in line:
                            lines.append(f"  {line}")
                            break
                else:
                    lines.append("  Build cache cleared")
            else:
                lines.append(f"  Error: {result.stderr.strip()}")
        return "\n".join(lines)
