# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
A redeploy must stop the previous instance before rebuilding in place.

The build runs in the same `src` tree the running app uses, and build outputs
land there (node_modules, dist, target/*.jar, esbuild binaries). If the old
instance is still alive while the rebuild runs, it holds those files open and
the rebuild corrupts: ENOTEMPTY (fastify), ETXTBSY (nuxtjs), "Invalid or corrupt
jarfile" (spring-boot), silent `astro build` failure (astro).

`do_deploy` now calls `stop_previous_instance(app)` before the prebuild hook;
these tests pin its guard so a live instance is always torn down first and a
first deploy stays a no-op.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from hop3.deployers import deployer as deployer_mod
from hop3.deployers.deployer import (
    _bounded_log_excerpt,
    _extract_app_error,
    stop_previous_instance,
)
from hop3.orm.app import AppStateEnum


def _fake_app(state: AppStateEnum) -> tuple[SimpleNamespace, list[str]]:
    calls: list[str] = []
    app = SimpleNamespace(
        name="myapp", run_state=state, stop=lambda: calls.append("stop")
    )
    return app, calls


@pytest.mark.parametrize(
    "state",
    [
        AppStateEnum.RUNNING,
        AppStateEnum.STARTING,
        AppStateEnum.STOPPING,
        AppStateEnum.FAILED,
    ],
)
def test_stops_a_live_previous_instance(state, monkeypatch) -> None:
    monkeypatch.setattr(deployer_mod, "log", lambda *_a, **_k: None)
    app, calls = _fake_app(state)
    stop_previous_instance(app)
    assert calls == ["stop"]


def test_first_deploy_is_a_noop(monkeypatch) -> None:
    # A freshly created app is recorded STOPPED; nothing to tear down.
    monkeypatch.setattr(deployer_mod, "log", lambda *_a, **_k: None)
    app, calls = _fake_app(AppStateEnum.STOPPED)
    stop_previous_instance(app)
    assert calls == []


def test_bounded_log_excerpt_keeps_head_and_tail() -> None:
    # A long crash log: exception at the top, throttle noise at the bottom.
    lines = ["RuntimeError: boom"] + [f"\tfrom frame{i}" for i in range(100)]
    out = _bounded_log_excerpt(lines, head=25, tail=20)
    assert out[0] == "RuntimeError: boom"  # the root error survives
    assert out[-1] == "\tfrom frame99"  # the tail survives
    assert any("omitted" in line for line in out)
    assert len(out) == 25 + 1 + 20


def test_bounded_log_excerpt_short_log_unchanged() -> None:
    lines = ["a", "b", "c"]
    assert _bounded_log_excerpt(lines) == lines


def test_extract_app_error_finds_rails_boot_failure() -> None:
    # The real shape: migration noise, then puma's crash line, then deep frames.
    lines = [
        "  Applying users.0004_alter_user_language... OK",
        "[41137] * Preloading application",
        (
            "[41137] ! Unable to load application: "
            "ActiveRecord::AdapterNotSpecified: The `cache` database is not configured"
        ),
        "      from .../railties/lib/rails/initializable.rb:102:in `run_initializers'",
        "      from config.ru:3:in `require_relative'",
    ]
    err = _extract_app_error(lines)
    assert err is not None
    assert "Unable to load application" in err
    assert "cache" in err


def test_extract_app_error_matches_exception_class() -> None:
    assert "NoMethodError" in (
        _extract_app_error(["ok", "boom: NoMethodError - undefined method"]) or ""
    )


def test_extract_app_error_none_when_clean() -> None:
    assert _extract_app_error(["Listening on 0.0.0.0:8000", "ready"]) is None


def test_extract_app_error_finds_missing_binary() -> None:
    line = "sh: 1: exec: _build/prod/rel/hop3_tuto_phoenix/bin/hop3_tuto_phoenix: not found"
    assert _extract_app_error(["starting", line, "[uwsgi-daemons] throttling"]) == line
