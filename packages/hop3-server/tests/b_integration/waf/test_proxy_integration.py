# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Standalone LeWAF proxy integration (ADR 050, Phase 1c).

Runs a real ``lewaf-proxy`` subprocess (via ``LeWafEngine.proxy_command``) in
front of a throwaway upstream and drives HTTP through it — no nginx, no Docker,
no hop3 deploy. Proves the load-bearing facts before the deploy wiring lands:

* the vendored OWASP CRS blocks attack classes (SQLi) and passes clean traffic
  (ADR acceptance #2);
* a forged ``X-Forwarded-For`` does **not** satisfy a network gate
  (Security invariant 1) — with ``trusted_proxy_count=1`` only the rightmost
  XFF entry (what the single nginx hop appends) is trusted.

Skipped where ``lewaf`` isn't installed (the ``waf`` extra is Python 3.12+).
"""

from __future__ import annotations

import contextlib
import socket
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import httpx
import pytest

pytest.importorskip("lewaf", reason="WAF extra (lewaf) not installed")

from hop3.plugins.waf.lewaf.engine import LeWafEngine
from hop3.project.schema import validate_hop3_toml

UPSTREAM_BODY = b"UPSTREAM-OK"
PROXY_BOOT_TIMEOUT = 30.0  # CRS parse + uvicorn boot on first start


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Upstream(BaseHTTPRequestHandler):
    def _ok(self) -> None:
        self.send_response(200)
        self.end_headers()
        self.wfile.write(UPSTREAM_BODY)

    def do_GET(self) -> None:
        self._ok()

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length", 0))
        if length:
            self.rfile.read(length)  # drain the body so the socket stays sane
        self._ok()

    def log_message(self, *args) -> None:  # silence the test log
        pass


@contextlib.contextmanager
def _upstream():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Upstream)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


@contextlib.contextmanager
def _proxy(policy_toml: dict, networks, tmp_path, banned=()):
    """Yield the base URL of a running lewaf-proxy fronting a dummy upstream."""
    policy = validate_hop3_toml({"waf": policy_toml}).waf
    engine = LeWafEngine(rules_dir=tmp_path)
    engine.configure_app("app", policy, networks)
    if banned:
        engine.write_bans("app", list(banned))
    port = _free_port()
    # Redirect proxy output to a file, NOT an unread PIPE: LeWAF's logging would
    # otherwise fill the pipe buffer and deadlock the process. The log is shown
    # on failure (never discarded) so a broken proxy is diagnosable.
    log_path = tmp_path / "proxy.log"
    with _upstream() as upstream_url, log_path.open("wb") as logf:
        cmd = engine.proxy_command("app", upstream_url, port)
        proc = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT)
        try:
            base = f"http://127.0.0.1:{port}"
            _wait_until_ready(proc, base, log_path)
            yield base
        finally:
            proc.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=10)
            if proc.poll() is None:
                proc.kill()


def _wait_until_ready(proc: subprocess.Popen, base: str, log_path) -> None:
    """Poll the proxy until it answers HTTP, failing loud (with logs) if not."""
    deadline = time.monotonic() + PROXY_BOOT_TIMEOUT
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            log = log_path.read_text(errors="replace") if log_path.exists() else ""
            pytest.fail(f"lewaf-proxy exited early (code {proc.returncode}):\n{log}")
        with contextlib.suppress(httpx.HTTPError):
            httpx.get(base + "/__ready__", timeout=1.0)
            return
        time.sleep(0.2)
    log = log_path.read_text(errors="replace") if log_path.exists() else ""
    pytest.fail(f"lewaf-proxy did not become ready in time:\n{log}")


# --- CRS attack blocking (acceptance #2) ----------------------------------


def test_crs_blocks_sqli_and_passes_clean_traffic(tmp_path):
    policy = {"enabled": True, "allow": ["/", "/items(/.*)?"]}
    with _proxy(policy, {}, tmp_path) as base:
        clean = httpx.get(f"{base}/items?id=42", timeout=10)
        assert clean.status_code == 200
        assert clean.content == UPSTREAM_BODY

        sqli = httpx.get(f"{base}/items?id=1%27%20OR%201%3D1--", timeout=10)
        assert sqli.status_code == 403
        assert UPSTREAM_BODY not in sqli.content  # never reached the upstream


def test_request_outside_allowlist_is_denied(tmp_path):
    with _proxy({"enabled": True, "allow": ["/", "/items(/.*)?"]}, {}, tmp_path) as base:
        assert httpx.get(f"{base}/wp-admin", timeout=10).status_code == 403


def test_owasp_attack_classes_are_blocked(tmp_path):
    """SQLi/XSS/path-traversal/RCE on an allowed path are blocked by the CRS;
    a legitimate request to the same path passes."""
    attacks = {
        "sqli": "/api?id=1%27%20OR%201%3D1--",
        "xss": "/api?q=%3Cscript%3Ealert(1)%3C%2Fscript%3E",
        "traversal": "/api?file=..%2F..%2F..%2Fetc%2Fpasswd",
        "rce": "/api?x=%3B%20cat%20%2Fetc%2Fpasswd",
    }
    with _proxy({"enabled": True, "allow": ["/", "/api(/.*)?"]}, {}, tmp_path) as base:
        for label, path in attacks.items():
            r = httpx.get(f"{base}{path}", timeout=10)
            assert r.status_code == 403, f"{label} not blocked"
            assert UPSTREAM_BODY not in r.content
        clean = httpx.get(f"{base}/api?id=42", timeout=10)
        assert clean.status_code == 200
        assert clean.content == UPSTREAM_BODY


# --- false-positive relief (ADR 050 §3 tuning) ----------------------------

_SQLI_BODY = b"id=1' OR '1'='1"
_FORM = {"content-type": "application/x-www-form-urlencoded"}


def test_attack_body_is_blocked_without_tuning(tmp_path):
    with _proxy({"enabled": True, "allow": ["/", "/up(/.*)?"]}, {}, tmp_path) as base:
        r = httpx.post(f"{base}/up", content=_SQLI_BODY, headers=_FORM, timeout=10)
        assert r.status_code == 403


def test_skip_body_inspection_lets_the_body_through(tmp_path):
    """A non-browser client (e.g. Nextcloud sync) posting WAF-hostile bodies on a
    scoped path passes once skip_body_inspection is tuned on — Security note: the
    body is trusted only where the operator opts in."""
    policy = {
        "enabled": True,
        "allow": ["/", "/up(/.*)?"],
        "tuning": [{"paths": ["/up(/.*)?"], "skip-body-inspection": True}],
    }
    with _proxy(policy, {}, tmp_path) as base:
        passed = httpx.post(f"{base}/up", content=_SQLI_BODY, headers=_FORM, timeout=10)
        assert passed.status_code == 200
        assert passed.content == UPSTREAM_BODY
        # the URI is still inspected — only the body is skipped on this path
        blocked = httpx.get(f"{base}/up?id=1%27%20OR%201%3D1--", timeout=10)
        assert blocked.status_code == 403


# --- network gate + trusted client IP (Security invariant 1) --------------

_GATE = {"enabled": True, "gate": [{"paths": ["/admin(/.*)?"], "require": "office"}]}
_NETS = {"office": ["203.0.113.0/24"]}


def test_gate_allows_office_client(tmp_path):
    """Rightmost XFF entry (what nginx appends) in the office net → allowed."""
    with _proxy(_GATE, _NETS, tmp_path) as base:
        r = httpx.get(
            f"{base}/admin", headers={"X-Forwarded-For": "203.0.113.5"}, timeout=10
        )
        assert r.status_code == 200
        assert r.content == UPSTREAM_BODY


def test_gate_rejects_forged_xff(tmp_path):
    """A client-forged office IP to the LEFT of the real (non-office) IP must
    not satisfy the gate — trusted_proxy_count=1 trusts only the rightmost."""
    with _proxy(_GATE, _NETS, tmp_path) as base:
        r = httpx.get(
            f"{base}/admin",
            headers={"X-Forwarded-For": "203.0.113.5, 198.51.100.7"},
            timeout=10,
        )
        assert r.status_code == 403
        assert UPSTREAM_BODY not in r.content


# --- ban enforcement (ADR 050 §4) -----------------------------------------


def test_banned_source_is_denied_even_on_allowed_path(tmp_path):
    """The ban denylist rejects a banned source before the allow/CRS rules;
    a non-banned source on the same allowed path passes through."""
    policy = {"enabled": True, "allow": ["/", "/ok(/.*)?"]}
    with _proxy(policy, {}, tmp_path, banned=["198.51.100.9"]) as base:
        banned = httpx.get(
            f"{base}/ok?id=42",
            headers={"X-Forwarded-For": "198.51.100.9"},
            timeout=10,
        )
        assert banned.status_code == 403
        assert UPSTREAM_BODY not in banned.content

        clean = httpx.get(
            f"{base}/ok?id=42",
            headers={"X-Forwarded-For": "203.0.113.1"},
            timeout=10,
        )
        assert clean.status_code == 200
        assert clean.content == UPSTREAM_BODY
