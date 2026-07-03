# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Unified diagnostic bundle (ADR 043 §7) — the silent-502 collector.

ONE target-agnostic collector, called on a *failure* before teardown. It runs a
fixed set of read-only commands over ``DeploymentTarget.exec_run`` (identical on
docker/ssh/hetzner), probes the nginx -> app proxy hop (the "silent-502" kernel),
classifies the failure, and writes a headline-first artifact bundle to
``~/.hop3/test-runs/<run_id>/``.

Functional core / imperative shell: the parsing, classification and headline are
pure functions over strings (unit-tested without any target); the only IO is
``exec_run`` (read-only) and a single directory write at the end.

This module must NOT import from ``hop3_testing.results`` (results imports Bundle,
never the reverse — avoids an import cycle).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Literal

from hop3_testing.bundle_ids import make_bundle_dir, make_run_id

if TYPE_CHECKING:
    from pathlib import Path

    from hop3_testing.targets.base import DeploymentTarget, HttpResponse

Classifier = Literal[
    "proxy-502",
    "build-failure",
    "addon-unreachable",
    "app-crash",
    "timeout",
    "indeterminate",
    "ok",
]
"""Failure buckets (ADR 043 §7.1). ``indeterminate`` = the probe was blind
(could not read the listen table without root) so we refuse a confident
proxy-502. ``ok`` is never persisted."""

DeployerKind = Literal["uwsgi", "docker", "static", "unknown"]

# Canonical section order == on-disk filenames (minus .txt). Single source.
SECTION_NAMES: tuple[str, ...] = (
    "proxy_probe",
    "nginx",
    "app",
    "journal",
    "resources",
    "build",
    "deploy",
    "http",
    "dns",
)

HOP3_ROOT = "/home/hop3"

# Suggested `why --section` per classifier (drives the headline pointer).
_SECTION_HINT: dict[str, str] = {
    "proxy-502": "proxy",
    "build-failure": "build",
    "addon-unreachable": "app",
    "app-crash": "app",
    "timeout": "journal",
    "indeterminate": "proxy",
    "ok": "app",
}


# --------------------------------------------------------------------------- #
# Value objects (functional core)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class ProxyProbe:
    """Result of the silent-502 kernel. Pure value over exec_run strings."""

    effective_uid: str
    deployer_kind: DeployerKind
    is_static: bool
    vhost_found: bool
    proxy_pass_port: int | None
    expected_port: int | None  # advisory (from deploy stdout); conf is ground truth
    listen_table_available: bool
    listen_ports: tuple[int, ...]
    listen_owner: str
    curl_status: int  # 0 == connection refused / nothing answering
    container_state: str  # docker only ("running 0", "exited 1", ...); else ""
    verdict: str

    def render(self) -> str:
        """Human-readable proxy_probe.txt body."""
        lines = [
            f"uid={self.effective_uid}",
            f"deployer kind: {self.deployer_kind}",
            f"vhost found: {self.vhost_found}",
            f"nginx proxy_pass port: {self.proxy_pass_port}",
            f"expected app port (advisory): {self.expected_port}",
            f"listen table readable: {self.listen_table_available}",
            f"127.0.0.1 LISTEN ports: {list(self.listen_ports) or '(none)'}",
            f"owner of proxy_pass port: {self.listen_owner or '(unknown)'}",
            f"curl 127.0.0.1:{self.proxy_pass_port}: {self.curl_status}",
        ]
        if self.deployer_kind == "docker":
            lines.append(f"container state: {self.container_state or '(unknown)'}")
        lines.append("")
        lines.append(f"verdict: {self.verdict}")
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class Bundle:
    """In-memory diagnostic bundle. All IO at the edges."""

    run_id: str
    app: str
    target_kind: str  # "docker" | "ssh" | "hetzner"
    classifier: Classifier
    headline: str
    sections: dict[str, str] = field(default_factory=dict)
    probe: ProxyProbe | None = None
    artifact_dir: Path | None = None

    @property
    def why(self) -> str:
        """The `hop3-test why` command that replays this bundle's most useful
        section.

        This is the test-context replacement for the server's own
        `hop3 app logs --app <app> --build` pointer: under `hop3-test` the app
        is destroyed right after the failure, so that pointer is dead — but the
        bundle is durable (every section is recorded under
        ``~/.hop3/test-runs/<run-id>/``).
        """
        section = _SECTION_HINT.get(self.classifier, "app")
        return f"hop3-test why {self.run_id} --section {section}"

    def manifest(self) -> dict:
        return {
            "schema_version": 1,
            "run_id": self.run_id,
            "app": self.app,
            "target_kind": self.target_kind,
            "classifier": self.classifier,
            "headline": self.headline,
            "sections": list(self.sections.keys()),
        }


# --------------------------------------------------------------------------- #
# Pure parsing helpers
# --------------------------------------------------------------------------- #
_PROXY_PASS_RE = re.compile(r"proxy_pass\s+https?://[\d.]+:(\d+)")
_UPSTREAM_RE = re.compile(
    r"upstream\s+\S+\s*\{[^}]*?server\s+127\.0\.0\.1:(\d+)", re.DOTALL
)
# A listener nginx's `proxy_pass http://127.0.0.1:PORT` can actually reach — not
# just a literal 127.0.0.1 bind. gunicorn/uwsgi default to `--bind 0.0.0.0:$PORT`
# (all interfaces, loopback included), so matching only "127.0.0.1:PORT" made the
# app's own port invisible and produced a FALSE proxy-502 for a healthy app that
# curl(127.0.0.1:PORT) reached fine. Accept the wildcard binds too (0.0.0.0, *,
# [::], ::). The peer column (`0.0.0.0:*`) can't false-match: its port is `*`,
# not digits.
_LISTEN_LINE_RE = re.compile(r"(?:127\.0\.0\.1|0\.0\.0\.0|\*|\[::\]|::):(\d+)")
_SS_OWNER_RE = re.compile(r'users:\(\("([^"]+)"')
_NETSTAT_OWNER_RE = re.compile(r"LISTEN\s+\d+/(\S+)")


def parse_proxy_pass_port(conf: str) -> int | None:
    """Extract the port nginx proxies to, from a rendered vhost.

    Prefers ``proxy_pass http://127.0.0.1:PORT`` and falls back to the app's own
    ``upstream { server 127.0.0.1:PORT; }`` block (uwsgi_pass path).
    """
    m = _PROXY_PASS_RE.search(conf)
    if not m:
        m = _UPSTREAM_RE.search(conf)
    return int(m.group(1)) if m else None


def _decode_proc_net_tcp(text: str) -> list[int]:
    """Decode LISTEN ports on 127.0.0.1 / 0.0.0.0 from /proc/net/tcp.

    Rows look like ``sl local_address rem_address st ...`` where local_address
    is ``HEXIP:HEXPORT`` (IP little-endian, port big-endian) and ``st == 0A``
    means LISTEN. ``0100007F`` = 127.0.0.1, ``00000000`` = 0.0.0.0.
    """
    ports: list[int] = []
    for line in text.splitlines():
        cols = line.split()
        if len(cols) < 4 or ":" not in cols[1]:
            continue
        local, state = cols[1], cols[3]
        if state != "0A":
            continue
        hexip, _, hexport = local.partition(":")
        if hexip.upper() not in {"0100007F", "00000000"}:
            continue
        try:
            ports.append(int(hexport, 16))
        except ValueError:
            continue
    return ports


def parse_listen_ports(text: str) -> tuple[tuple[int, ...], bool, dict[int, str]]:
    """Parse loopback-reachable LISTEN ports from ss / netstat / /proc/net/tcp.

    "Loopback-reachable" = bound to 127.0.0.1 OR a wildcard (0.0.0.0 / * / [::] /
    ::), since a connect to 127.0.0.1:PORT reaches all of those. Matching only a
    literal 127.0.0.1 bind missed apps that listen on 0.0.0.0:$PORT (the gunicorn
    default) and mislabelled them proxy-502.

    Returns ``(ports, table_available, owner_by_port)``. ``table_available`` is
    False when nothing parseable was produced (no tool present + non-root) — the
    classifier uses that to refuse a confident proxy-502.
    """
    stripped = text.strip()
    if not stripped or stripped.startswith("("):
        return (), False, {}

    # /proc/net/tcp fallback (no LISTEN keyword; hex addresses + a header).
    if "LISTEN" not in text and ("local_address" in text or ":" in stripped):
        proc_ports = _decode_proc_net_tcp(text)
        if proc_ports:
            return tuple(sorted(set(proc_ports))), True, {}
        # A header-only /proc dump still means the table was readable.
        if "local_address" in text:
            return (), True, {}
        return (), False, {}

    # ss / netstat text path.
    ports: list[int] = []
    owners: dict[int, str] = {}
    saw_listen = False
    for line in text.splitlines():
        if "LISTEN" not in line:
            continue
        saw_listen = True
        for m in _LISTEN_LINE_RE.finditer(line):
            port = int(m.group(1))
            ports.append(port)
            owner = _SS_OWNER_RE.search(line) or _NETSTAT_OWNER_RE.search(line)
            if owner:
                owners[port] = owner.group(1)
    return tuple(sorted(set(ports))), saw_listen, owners


# --------------------------------------------------------------------------- #
# Pure classification + headline
# --------------------------------------------------------------------------- #
_BUILD_ERR_RE = re.compile(
    r"\berror:|\bTraceback\b|non-zero exit|failed to build|command not found|"
    r"Deploy failed|Builder can't",
    re.IGNORECASE,
)
_ADDON_ERR_RE = re.compile(
    r"could not connect to server|connection refused.*:(5432|3306|6379)|"
    r"psycopg|redis\.exceptions\.ConnectionError|OperationalError",
    re.IGNORECASE,
)
_CRASH_RE = re.compile(
    r"Traceback \(most recent call last\)|Segmentation fault|"
    r"ModuleNotFoundError|ImportError|uWSGI.*died|worker.*killed",
    re.IGNORECASE,
)


def _build_failed(build: str, deploy: str) -> bool:
    return bool(_BUILD_ERR_RE.search(build) or _BUILD_ERR_RE.search(deploy))


def _addon_unreachable(app: str) -> bool:
    return bool(_ADDON_ERR_RE.search(app))


def _docker_down(probe: ProxyProbe) -> bool:
    state = probe.container_state.strip()
    return (state != "" and not state.startswith("running 0")) or probe.curl_status == 0


def _proxy_mismatch(probe: ProxyProbe) -> bool:
    """nginx points at a port nothing is listening on (and we could see)."""
    if probe.proxy_pass_port is None or not probe.listen_table_available:
        return False
    return probe.proxy_pass_port not in probe.listen_ports


def _app_crashed(app: str, probe: ProxyProbe | None) -> bool:
    if _CRASH_RE.search(app):
        return True
    if probe is not None and probe.listen_table_available and probe.curl_status == 0:
        # non-docker: bound nowhere / not answering with a readable table
        return probe.deployer_kind != "docker"
    return False


def classify(  # noqa: PLR0911 - one return per precedence rule is the clearest form
    sections: dict[str, str],
    probe: ProxyProbe | None,
    *,
    kind: DeployerKind,
    http_front: HttpResponse | None,
    hint: Classifier | None = None,
) -> Classifier:
    """Map collected signals to a failure bucket. Pinned precedence (ADR 043)."""
    if hint:
        return hint
    if _build_failed(sections.get("build", ""), sections.get("deploy", "")):
        return "build-failure"
    if _addon_unreachable(sections.get("app", "")):
        return "addon-unreachable"
    if probe is not None and probe.is_static:
        # static app: a front 502 with no backend is a serve/config issue.
        if http_front is not None and http_front.status >= 500:
            return "app-crash"
        return "ok"
    if kind == "docker" and probe is not None and _docker_down(probe):
        return "app-crash"
    if (
        probe is not None
        and not probe.listen_table_available
        and probe.effective_uid != "root"
    ):
        return "indeterminate"  # blind probe -> never blame the proxy
    if probe is not None and _proxy_mismatch(probe):
        return "proxy-502"
    if _app_crashed(sections.get("app", ""), probe):
        return "app-crash"
    if http_front is not None and http_front.status == 0:
        return "timeout"
    return "ok"


_ICON: dict[str, str] = {"indeterminate": "?", "ok": "✓"}


def build_headline(
    *,
    classifier: Classifier,
    app: str,
    run_id: str,
    probe: ProxyProbe | None,
    sections: dict[str, str],
    http_front: HttpResponse | None,
) -> str:
    """Render the <=12-line, headline-first failure summary."""
    icon = _ICON.get(classifier, "✗")
    verdict = (
        probe.verdict
        if probe is not None and classifier in {"proxy-502", "indeterminate"}
        else _root_cause(sections, http_front)
    )
    lines = [
        f"{icon} {classifier} — {app}",
        f"run-id: {run_id}",
        f"verdict: {verdict}",
        "",
    ]
    lines.extend(_signal_lines(classifier, probe, http_front))
    lines.append("")
    section = _SECTION_HINT.get(classifier, "app")
    lines.append(f"why: hop3-test why {run_id} --section {section}")
    return "\n".join(lines)


def _root_cause(sections: dict[str, str], http_front: HttpResponse | None) -> str:
    """A one-line cause for non-proxy classifiers."""
    build = sections.get("build", "")
    m = _BUILD_ERR_RE.search(build)
    if m:
        line = next((ln for ln in build.splitlines() if _BUILD_ERR_RE.search(ln)), "")
        return line.strip()[:160] or "build failed"
    if http_front is not None:
        return f"front-door HTTP {http_front.status}"
    return "see sections below"


def _signal_lines(
    classifier: Classifier,
    probe: ProxyProbe | None,
    http_front: HttpResponse | None,
) -> list[str]:
    lines: list[str] = []
    if probe is not None and classifier in {"proxy-502", "indeterminate", "app-crash"}:
        lines.append(f"nginx proxy_pass: 127.0.0.1:{probe.proxy_pass_port}")
        listen = list(probe.listen_ports) or "(none on 127.0.0.1)"
        avail = "" if probe.listen_table_available else " [table unreadable]"
        lines.append(f"app LISTEN ports:  {listen}{avail}")
        lines.append(f"curl 127.0.0.1:{probe.proxy_pass_port}: {probe.curl_status}")
        if probe.deployer_kind == "docker":
            lines.append(f"container state:   {probe.container_state or '(unknown)'}")
        lines.append(
            f"deployer kind:     {probe.deployer_kind}  [uid={probe.effective_uid}]"
        )
    if http_front is not None:
        lines.append(f"front-door:        HTTP {http_front.status}")
    return lines[:6]


# --------------------------------------------------------------------------- #
# Collectors (imperative shell — read-only exec_run)
# --------------------------------------------------------------------------- #
def _exec(target: DeploymentTarget, cmd: str) -> tuple[int, str, str]:
    """Run a command, never raising (per-section isolation)."""
    try:
        return target.exec_run(cmd)
    except Exception as e:  # diagnostics must never crash the run
        return 1, "", str(e)


def _section_body(target: DeploymentTarget, cmd: str) -> str:
    _, out, err = _exec(target, cmd)
    body = (out or "").rstrip()
    if not body and err:
        body = f"(stderr) {err.rstrip()}"
    return body or "(empty)"


def _detect_kind(target: DeploymentTarget, app: str) -> DeployerKind:
    _, out, _ = _exec(
        target,
        f"if ls {HOP3_ROOT}/uwsgi-enabled/{app}*.ini >/dev/null 2>&1; then echo uwsgi; "
        f"elif command -v docker >/dev/null 2>&1 && "
        f"docker ps -a --filter name={app} --format '{{{{.Names}}}}' 2>/dev/null "
        f"| grep -q .; then echo docker; "
        f"elif grep -q 'HOP3_STATIC_ONLY' {HOP3_ROOT}/nginx/{app}.conf 2>/dev/null; "
        f"then echo static; else echo unknown; fi",
    )
    val = (out or "").strip()
    return val if val in {"uwsgi", "docker", "static"} else "unknown"  # type: ignore[return-value]


def _collect_sections(
    target: DeploymentTarget,
    app: str,
    *,
    deploy_logs: str,
    http_front: HttpResponse | None,
) -> dict[str, str]:
    """Collect every section except proxy_probe (built from the probe)."""
    sections: dict[str, str] = {}

    sections["nginx"] = _section_body(
        target,
        'echo "uid=$(id -un)";'
        f"echo '=== rendered conf ==='; cat {HOP3_ROOT}/nginx/{app}.conf 2>&1 "
        "|| echo '(no nginx conf)';"
        "echo '=== nginx error.log (tail 200) ==='; "
        "tail -200 /var/log/nginx/error.log 2>&1 "
        "|| echo '(no error.log / permission denied — needs root)';"
        "echo '=== nginx access.log (tail 80) ==='; "
        "tail -80 /var/log/nginx/access.log 2>&1 || echo '(no access.log)'",
    )

    sections["app"] = _section_body(
        target,
        'echo "uid=$(id -un)";'
        f"echo '=== app dir ==='; ls -la {HOP3_ROOT}/apps/{app}/ 2>&1 | head -30;"
        "echo '=== app logs (tail 200) ==='; "
        f"tail -n 200 {HOP3_ROOT}/apps/{app}/log/*.log 2>&1 || echo '(no app logs)';"
        "echo '=== uwsgi ini ==='; "
        f"cat {HOP3_ROOT}/uwsgi-enabled/{app}*.ini 2>&1 "
        f"|| cat {HOP3_ROOT}/uwsgi-available/{app}*.ini 2>&1 || echo '(no uwsgi ini)';"
        "echo '=== docker state ==='; "
        f"docker ps -a --filter name={app} 2>/dev/null || echo '(no docker)';"
        "echo '=== docker logs (tail 100) ==='; "
        f"docker logs --tail 100 $(docker ps -aq --filter name={app} 2>/dev/null "
        "| head -1) 2>&1 || echo '(no docker logs)';"
        # For nix apps: resolve the GC-root symlink and verify every store path
        # the runtime references still exists. A MISSING line here is the
        # smoking gun for a garbage-collected closure (e.g. forgejo's wrapped
        # ${forgejo}/bin/forgejo → "No such file or directory").
        "echo '=== nix result (nix apps) ==='; "
        f"R={HOP3_ROOT}/apps/{app}/.nix-result; "
        'if [ -e "$R" ] || [ -L "$R" ]; then '
        'T=$(readlink -f "$R"); echo "link -> $T"; '
        'ls -la "$T/bin" 2>&1 | head -20; '
        "echo '--- runtime.json store paths (exist?) ---'; "
        "grep -oE '/nix/store/[a-z0-9]{32}-[a-zA-Z0-9._+-]+' "
        '"$T/hop3/runtime.json" 2>/dev/null | sort -u | '
        'while read -r P; do if [ -e "$P" ]; then echo "OK      $P"; '
        'else echo "MISSING $P"; fi; done; '
        "else echo '(not a nix app / no .nix-result)'; fi;"
        "echo '=== listen check ==='; "
        "ss -ltnp 2>/dev/null || netstat -tlnp 2>/dev/null "
        "|| echo '(ss/netstat unavailable — see proxy_probe.txt)'",
    )

    sections["journal"] = _section_body(
        target,
        'echo "uid=$(id -un)";'
        "if command -v journalctl >/dev/null 2>&1; then "
        "echo '=== hop3-server ==='; "
        "journalctl -u hop3-server -n 200 --no-pager 2>&1 "
        "|| echo '(journalctl needs root)';"
        "echo '=== hop3-rootd ==='; "
        "journalctl -u hop3-rootd -n 100 --no-pager 2>&1 || echo '(none)';"
        "else echo '=== supervisor hop3-server ==='; "
        "tail -200 /var/log/supervisor/hop3-server.log 2>&1 || echo '(none)';"
        "tail -200 /var/log/supervisor/hop3-server_err.log 2>&1 || echo '(none)'; fi",
    )

    # Host resource state — disk/inodes/memory + nix GC roots + OOM kills. A
    # long run accumulates disk (caches, store, app trees); when it runs low,
    # builds truncate (spring-boot "zip file is empty"), nix auto-GC deletes
    # running apps' closures (forgejo), and the OOM killer fells builds (astro
    # exits with empty output). Capturing this makes those self-evident instead
    # of black boxes. All commands are fast (no `du` over big trees).
    sections["resources"] = _section_body(
        target,
        'echo "uid=$(id -un)";'
        "echo '=== df -h ==='; df -h 2>&1;"
        "echo '=== df -i (inodes) ==='; df -i 2>&1 | head -20;"
        "echo '=== free -m ==='; free -m 2>&1 || echo '(free unavailable)';"
        "echo '=== nix gcroots/auto (deployed-app roots) ==='; "
        "ls -la /nix/var/nix/gcroots/auto/ 2>/dev/null | head -50 "
        "|| echo '(no nix gcroots/auto)';"
        "echo '=== OOM kills (dmesg) ==='; "
        "dmesg -T 2>/dev/null | grep -iE 'killed process|out of memory|oom-kill' "
        "| tail -10 || echo '(dmesg unavailable or no OOM)'",
    )

    sections["build"] = _section_body(
        target,
        'echo "uid=$(id -un)";'
        f"if [ -f {HOP3_ROOT}/apps/{app}/log/build.log ]; then "
        f"tail -200 {HOP3_ROOT}/apps/{app}/log/build.log 2>&1; "
        "else echo '(no build.log)'; fi",
    )

    sections["dns"] = _section_body(
        target,
        'echo "uid=$(id -un)";'
        f"host=$(grep -E '^HOST_NAME=' {HOP3_ROOT}/apps/{app}/ENV 2>/dev/null "
        "| cut -d= -f2- | tr -d \"'\\\"\" | awk '{print $1}');"
        'echo "HOST_NAME=$host"; '
        '[ -n "$host" ] && getent hosts "$host" 2>&1 '
        "|| echo '(no HOST_NAME in ENV or unresolved — docker uses *.test.local)'",
    )

    sections["deploy"] = deploy_logs.rstrip() or "(no deploy log captured)"
    sections["http"] = _format_http(http_front)
    return sections


def _format_http(http_front: HttpResponse | None) -> str:
    if http_front is None:
        return "(front-door probe not run)"
    headers = "\n".join(f"{k}: {v}" for k, v in http_front.headers.items())
    return (
        f"status: {http_front.status}\n"
        f"headers:\n{headers or '(none)'}\n"
        f"body[:500]:\n{http_front.body[:500]}"
    )


def _probe_proxy(
    target: DeploymentTarget,
    app: str,
    *,
    kind: DeployerKind,
    expected_port: int | None,
) -> ProxyProbe:
    """The silent-502 kernel. Always returns a ProxyProbe; never raises."""
    _, uid_out, _ = _exec(target, "id -un")
    uid = (uid_out or "").strip() or "unknown"

    _, conf, _ = _exec(target, f"cat {HOP3_ROOT}/nginx/{app}.conf 2>/dev/null")
    vhost_found = bool(conf.strip())
    is_static = kind == "static" or (
        vhost_found
        and "proxy_pass" not in conf
        and "uwsgi_pass" not in conf
        and "upstream" not in conf
    )
    proxy_pass_port = parse_proxy_pass_port(conf) if vhost_found else None

    _, listen_out, _ = _exec(
        target,
        "ss -ltnp 2>/dev/null || netstat -tlnp 2>/dev/null "
        "|| cat /proc/net/tcp 2>/dev/null",
    )
    listen_ports, table_ok, owners = parse_listen_ports(listen_out)
    listen_owner = owners.get(proxy_pass_port or -1, "")

    container_state = ""
    if kind == "docker":
        _, cs_out, _ = _exec(
            target,
            "docker inspect -f '{{.State.Status}} {{.State.ExitCode}}' "
            f"$(docker ps -aq --filter name={app} 2>/dev/null | head -1) "
            "2>/dev/null || echo '(no container)'",
        )
        container_state = (cs_out or "").strip()

    curl_status = 0
    if proxy_pass_port is not None:
        _, curl_out, _ = _exec(
            target,
            "curl -s -o /dev/null -w '%{http_code}' --max-time 5 "
            f"http://127.0.0.1:{proxy_pass_port}/ || echo 000",
        )
        try:
            curl_status = int((curl_out or "0").strip())
        except ValueError:
            curl_status = 0

    verdict = _probe_verdict(
        kind=kind,
        is_static=is_static,
        vhost_found=vhost_found,
        proxy_pass_port=proxy_pass_port,
        table_ok=table_ok,
        listen_ports=listen_ports,
        curl_status=curl_status,
        container_state=container_state,
        uid=uid,
    )
    return ProxyProbe(
        effective_uid=uid,
        deployer_kind=kind,
        is_static=is_static,
        vhost_found=vhost_found,
        proxy_pass_port=proxy_pass_port,
        expected_port=expected_port,
        listen_table_available=table_ok,
        listen_ports=listen_ports,
        listen_owner=listen_owner,
        curl_status=curl_status,
        container_state=container_state,
        verdict=verdict,
    )


def _probe_verdict(  # noqa: PLR0911 - one return per verdict case is clearest
    *,
    kind: DeployerKind,
    is_static: bool,
    vhost_found: bool,
    proxy_pass_port: int | None,
    table_ok: bool,
    listen_ports: tuple[int, ...],
    curl_status: int,
    container_state: str,
    uid: str,
) -> str:
    if not vhost_found:
        return "no nginx vhost for this app (proxy never configured / HOST_NAME unset)"
    if is_static:
        return "static app, nginx serves files directly (proxy probe N/A)"
    if not table_ok and uid != "root":
        return (
            "INDETERMINATE: could not read the listen table (need root / iproute2); "
            f"curl={curl_status}"
        )
    if kind == "docker":
        if container_state and not container_state.startswith("running 0"):
            return (
                f"docker container not healthy: {container_state} (curl={curl_status})"
            )
        if curl_status == 0:
            return f"docker app not answering on 127.0.0.1:{proxy_pass_port} (curl=000)"
    if proxy_pass_port is not None and table_ok and proxy_pass_port not in listen_ports:
        return f"nginx proxies to 127.0.0.1:{proxy_pass_port} but nothing LISTENs there"
    if curl_status and 200 <= curl_status < 500:
        return (
            f"backend reachable on 127.0.0.1:{proxy_pass_port} (curl {curl_status}); "
            "a front-door 502 is upstream of nginx (server_name / DNS)"
        )
    if curl_status == 0:
        return f"backend bound but not answering on 127.0.0.1:{proxy_pass_port}"
    return f"proxy_pass 127.0.0.1:{proxy_pass_port}, curl={curl_status}"


# --------------------------------------------------------------------------- #
# Writer (imperative shell)
# --------------------------------------------------------------------------- #
def write_bundle(bundle: Bundle, base_dir: Path | None = None) -> Bundle:
    """Persist the bundle to a collision-safe directory.

    Returns a NEW Bundle with the (possibly collision-extended) final run_id and
    its ``artifact_dir`` set. The directory basename always equals the returned
    ``run_id``.
    """
    final_run_id, run_dir = make_bundle_dir(bundle.run_id, base_dir)
    bundle = replace(bundle, run_id=final_run_id, artifact_dir=run_dir)
    for name in SECTION_NAMES:
        (run_dir / f"{name}.txt").write_text(
            bundle.sections.get(name, "(not collected)")
        )
    (run_dir / "manifest.json").write_text(json.dumps(bundle.manifest(), indent=2))
    return bundle


# --------------------------------------------------------------------------- #
# Public entry
# --------------------------------------------------------------------------- #
def collect_diagnostic_bundle(
    target: DeploymentTarget,
    app: str,
    *,
    classifier_hint: Classifier | None = None,
    deploy_logs: str = "",
    http_front: HttpResponse | None = None,
    expected_port: int | None = None,
    target_kind: str = "docker",
    base_dir: Path | None = None,
    persist: bool = True,
    force_persist: bool = False,
) -> Bundle:
    """Collect a target-agnostic diagnostic bundle BEFORE teardown.

    Only call this on a real failure. By default an ``ok`` classification is not
    written to disk — but some failures classify ``ok`` at the runtime layer
    (the app serves fine; a check.py body assertion or HTTP `contains` is what
    failed). For those, pass ``force_persist=True`` so the bundle is still
    written and ``why <run-id>`` can replay it. Never raises: per-section
    isolation + a probe that degrades to ``indeterminate`` rather than emitting a
    confident-but-wrong verdict.
    """
    kind = _detect_kind(target, app)
    sections = _collect_sections(
        target, app, deploy_logs=deploy_logs, http_front=http_front
    )
    probe = _probe_proxy(target, app, kind=kind, expected_port=expected_port)
    sections["proxy_probe"] = probe.render()

    classifier = classify(
        sections, probe, kind=kind, http_front=http_front, hint=classifier_hint
    )
    run_id = make_run_id(app)
    headline = build_headline(
        classifier=classifier,
        app=app,
        run_id=run_id,
        probe=probe,
        sections=sections,
        http_front=http_front,
    )
    bundle = Bundle(
        run_id=run_id,
        app=app,
        target_kind=target_kind,
        classifier=classifier,
        headline=headline,
        sections=sections,
        probe=probe,
    )
    if persist and (force_persist or classifier != "ok"):
        bundle = write_bundle(bundle, base_dir)
    return bundle
