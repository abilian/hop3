# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Proxy/cert setup failures must be LOUD on the uwsgi path.

A swallowed proxy-setup error is how edrix.eu shipped a self-signed cert under a
green deploy. ``AppLauncher._setup_proxy`` must propagate the failure (so the
deploy fails), not log-and-continue.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from hop3.run.spawn import AppLauncher


class _BoomProxy:
    def setup(self) -> None:
        msg = "certbot failed"
        raise RuntimeError(msg)


def _bare_launcher() -> AppLauncher:
    """
    An AppLauncher with just the attrs _setup_proxy reads (skips __post_init__).

    ``workers`` is a property over artifact/config, so we seed those instead.
    """
    launcher = AppLauncher.__new__(AppLauncher)
    launcher.app_name = "myapp"
    launcher.app = object()
    launcher.env = {}
    launcher.artifact = None
    launcher.config = SimpleNamespace(workers={"web": "python"})
    return launcher


def test_setup_proxy_propagates_failure(monkeypatch):
    monkeypatch.setattr(
        "hop3.run.spawn.get_proxy_strategy", lambda *a, **k: _BoomProxy()
    )
    with pytest.raises(RuntimeError, match="certbot failed"):
        _bare_launcher()._setup_proxy("example.com")


def test_setup_proxy_skips_without_hostname(monkeypatch):
    # The no-hostname / catch-all guard still short-circuits: no proxy, no raise.
    def _must_not_run(*_a, **_k):
        msg = "get_proxy_strategy must not be called without a real hostname"
        raise AssertionError(msg)

    monkeypatch.setattr("hop3.run.spawn.get_proxy_strategy", _must_not_run)
    launcher = _bare_launcher()
    launcher._setup_proxy("_")
    launcher._setup_proxy("")
