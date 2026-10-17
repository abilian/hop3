# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
An app without an HTTP port is checked through nginx on the target, a container
included.

Containers had a second, client-side checker. It kept 4096 characters of the
body and followed redirects before matching the status, so on Docker wordpress
"did not contain 'Hello world'" and kanboard's `status = 302` read as a 200,
while the same recipes passed on a server.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from hop3_testing.apps.catalog import AppSource
from hop3_testing.apps.deployment import DeploymentSession

_BODY = "<style>" + "x" * 50_000 + "</style><h2>Hello world!</h2>"


class _Container:
    """Answers the curl the harness runs on the target, as nginx would."""

    info = SimpleNamespace(is_container=True)

    def exec_run(self, cmd: str) -> tuple[int, str, str]:
        if "%{http_code}" in cmd:
            return 0, "302", ""
        return 0, _BODY, ""


def _session(tmp_path) -> DeploymentSession:
    app = AppSource(name="kanboard", path=tmp_path)
    session = DeploymentSession(app, cast("Any", _Container()), app_name="kb-1")
    session.deployed = True
    session._app_port = 40275
    session._app_protocol = "fastcgi"
    return session


def test_the_status_is_the_unfollowed_one(tmp_path):
    result = _session(tmp_path).test_http_detailed(path="/", expected_status=302)
    assert result["passed"], result["message"]


def test_the_body_is_not_cut_at_a_preview(tmp_path):
    result = _session(tmp_path).test_http_detailed(path="/", expected_status=302)
    assert "Hello world" in result["details"]["body_preview"]


class _SlowBody(_Container):
    """The status answers in time; the body fetch times out (curl exit 28)."""

    def exec_run(self, cmd: str) -> tuple[int, str, str]:
        if "%{http_code}" in cmd:
            return 0, "200", ""
        return 28, "", "curl: (28) Operation timed out"


def test_a_body_that_could_not_be_fetched_is_not_an_empty_page(tmp_path):
    session = _session(tmp_path)
    session.target = cast("Any", _SlowBody())

    result = session.test_http_detailed(path="/", expected_status=200)

    assert not result["passed"]
    assert "curl exit 28" in result["message"]
    assert "timed out" in result["message"]


class _EmptyBody(_Container):
    """A 200 with nothing in it, as Uptime Kuma's /dashboard once answered."""

    def exec_run(self, cmd: str) -> tuple[int, str, str]:
        if "%{http_code}" in cmd:
            return 0, "200", ""
        if "-D -" in cmd:
            return 0, "HTTP/1.1 200 OK\r\nContent-Length: 0\r\n", ""
        return 0, "", ""


def test_an_empty_body_comes_with_its_headers(tmp_path):
    session = _session(tmp_path)
    session.target = cast("Any", _EmptyBody())

    result = session.test_http_detailed(path="/", expected_status=200)

    assert result["details"]["body_preview"] == ""
    assert "Content-Length: 0" in result["details"]["headers"]
