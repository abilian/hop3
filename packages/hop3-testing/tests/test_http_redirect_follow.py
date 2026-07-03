# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""A `contains` assertion must follow redirects; the status check must not.

Apps whose entry point 302/307-redirects (kanboard → board, easy-appointments →
installer) return an EMPTY body on the 3xx itself, so a `contains` check against
that response always failed even though the app served the content one hop away.
The body fetch now follows redirects (-L) while the status probe does not — so a
validation can still assert the immediate redirect (`status = 302`) AND assert
content behind it (`contains = "Kanboard"`).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from hop3_testing.apps.deployment import DeploymentSession


def _run(status_probe_code: str, body: str, expected_status):
    calls: list[str] = []

    def exec_run(cmd: str):
        calls.append(cmd)
        # The status probe is the one writing just the code (-o /dev/null -w).
        if "-o /dev/null" in cmd:
            return (0, status_probe_code, "")
        return (0, body, "")

    fake = SimpleNamespace(
        target=SimpleNamespace(exec_run=exec_run),
        console=SimpleNamespace(
            info=lambda *a, **k: None,
            success=lambda *a, **k: None,
            debug=lambda *a, **k: None,
        ),
    )
    result: dict[str, Any] = {"passed": False, "message": "", "details": {}}
    out = DeploymentSession._test_http_via_ssh(
        fake, 5000, "/", expected_status, 1, result
    )
    return out, calls


def test_status_probe_does_not_follow_body_fetch_does():
    out, calls = _run("302", "<title>Kanboard</title>", expected_status=302)

    status_cmd = next(c for c in calls if "-o /dev/null" in c)
    body_cmd = next(c for c in calls if "-o /dev/null" not in c)
    # status assertion sees the immediate 302 (no -L), so `status = 302` holds
    assert "-L" not in status_cmd
    # content is fetched by following the redirect to the real page
    assert "-L" in body_cmd
    assert out["passed"] is True
    assert out["details"]["body_preview"] == "<title>Kanboard</title>"


def test_followed_body_is_captured_for_a_307_entry_redirect():
    # easy-appointments: 307 to the installer; the followed body carries content.
    out, calls = _run("307", "Easy!Appointments installer", expected_status=307)
    assert out["passed"] is True
    assert "Easy!Appointments" in out["details"]["body_preview"]
    assert "-L" in next(c for c in calls if "-o /dev/null" not in c)
