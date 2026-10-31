# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
An app proxied by hostname with no worker answering HTTP is refused early.

The check used to fire for Python artifact kinds only: a Go or Node app with
the same mistake got no word before its 502. Then it was a warning, and the
deploy went on to publish the 502.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from hop3.lib.console import Abort
from hop3.run.spawn import AppLauncher


def _launcher(kind: str, workers: dict[str, str]) -> AppLauncher:
    launcher = AppLauncher.__new__(AppLauncher)
    launcher.app_name = "myapp"
    launcher.config = SimpleNamespace(workers={})
    launcher.artifact = SimpleNamespace(
        kind=kind, runtime=SimpleNamespace(workers=workers)
    )
    return launcher


@pytest.mark.parametrize("kind", ["python", "go", "node", "generic"])
def test_no_http_worker_is_reported_whatever_the_language(kind: str) -> None:
    reason = _launcher(kind, {"worker": "run-queue"}).unrouted_reason("a.example")
    assert "no worker that answers HTTP" in reason


@pytest.mark.parametrize("workers", [{"web": "serve"}, {"static": "public"}])
def test_a_web_or_static_worker_is_routed(workers: dict[str, str]) -> None:
    assert _launcher("go", workers).unrouted_reason("a.example") == ""


@pytest.mark.parametrize("host_name", ["", "_"])
def test_an_app_without_a_hostname_needs_no_http_worker(host_name: str) -> None:
    assert _launcher("go", {"worker": "run-queue"}).unrouted_reason(host_name) == ""


def test_a_hostname_that_would_route_to_nothing_stops_the_deploy() -> None:
    launcher = _launcher("go", {"worker": "run-queue"})
    with pytest.raises(Abort, match="no worker that answers HTTP"):
        launcher.refuse_unrouted_host("a.example")
    launcher.refuse_unrouted_host("")  # no hostname: nothing to route
