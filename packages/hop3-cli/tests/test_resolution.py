# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for implicit app resolution (ADR 036 D7)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from hop3_cli.core.resolution import AppResolution, resolve_app

if TYPE_CHECKING:
    from pathlib import Path


def _fake_config(context_name: str = "prod", default_app: str = "") -> MagicMock:
    """Build a minimal Config-like mock for the resolver."""
    cfg = MagicMock()
    cfg.get_current_context_name.return_value = context_name
    cfg.get_default_app.return_value = default_app
    return cfg


def test_flag_wins_over_everything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Explicit --app always wins."""
    monkeypatch.setenv("HOP3_APP", "from-env")
    (tmp_path / ".hop3-app").write_text("from-file\n")
    cfg = _fake_config(default_app="from-context")

    r = resolve_app(
        cli_app="from-flag",
        config=cfg,
        cwd=tmp_path,
        home=tmp_path,
    )
    assert r.resolved
    assert r.app == "from-flag"
    assert "flag" in r.source.lower()


def test_env_var_beats_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOP3_APP", "from-env")
    (tmp_path / ".hop3-app").write_text("from-file\n")
    cfg = _fake_config(default_app="from-context")

    r = resolve_app(cli_app=None, config=cfg, cwd=tmp_path, home=tmp_path)
    assert r.app == "from-env"
    assert "HOP3_APP" in r.source


def test_dotfile_beats_context_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HOP3_APP", raising=False)
    (tmp_path / ".hop3-app").write_text("from-file\n")
    cfg = _fake_config(default_app="from-context")

    r = resolve_app(cli_app=None, config=cfg, cwd=tmp_path, home=tmp_path)
    assert r.app == "from-file"
    assert ".hop3-app" in r.source


def test_dotfile_search_upward(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`.hop3-app` in an ancestor directory is found."""
    monkeypatch.delenv("HOP3_APP", raising=False)
    (tmp_path / ".hop3-app").write_text("from-ancestor\n")
    sub = tmp_path / "a" / "b" / "c"
    sub.mkdir(parents=True)
    cfg = _fake_config(default_app="")

    r = resolve_app(cli_app=None, config=cfg, cwd=sub, home=tmp_path)
    assert r.app == "from-ancestor"


def test_dotfile_search_stops_at_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Search doesn't escape above $HOME."""
    monkeypatch.delenv("HOP3_APP", raising=False)
    # We can't easily place a .hop3-app outside tmp_path with pytest fixtures,
    # but we CAN verify the symmetric property: with nothing inside tmp_path,
    # resolution must fail rather than wander up the filesystem.
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    cfg = _fake_config(default_app="")

    r = resolve_app(cli_app=None, config=cfg, cwd=sub, home=tmp_path)
    assert not r.resolved
    assert r.app is None


def test_hop3_toml_cli_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOP3_APP", raising=False)
    (tmp_path / "hop3.toml").write_text('[cli]\napp = "from-toml"\n')
    cfg = _fake_config(default_app="from-context")

    r = resolve_app(cli_app=None, config=cfg, cwd=tmp_path, home=tmp_path)
    assert r.app == "from-toml"
    assert "hop3.toml" in r.source


def test_dotfile_beats_hop3_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`.hop3-app` has higher priority than hop3.toml."""
    monkeypatch.delenv("HOP3_APP", raising=False)
    (tmp_path / ".hop3-app").write_text("from-file\n")
    (tmp_path / "hop3.toml").write_text('[cli]\napp = "from-toml"\n')
    cfg = _fake_config(default_app="")

    r = resolve_app(cli_app=None, config=cfg, cwd=tmp_path, home=tmp_path)
    assert r.app == "from-file"


def test_context_default_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HOP3_APP", raising=False)
    cfg = _fake_config(context_name="prod", default_app="from-context")

    r = resolve_app(cli_app=None, config=cfg, cwd=tmp_path, home=tmp_path)
    assert r.app == "from-context"
    assert "prod" in r.source


def test_nothing_resolves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOP3_APP", raising=False)
    cfg = _fake_config(context_name="", default_app="")

    r = resolve_app(cli_app=None, config=cfg, cwd=tmp_path, home=tmp_path)
    assert not r.resolved
    assert r.app is None


def test_trace_captured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOP3_APP", raising=False)
    cfg = _fake_config(default_app="from-context")

    r = resolve_app(cli_app=None, config=cfg, cwd=tmp_path, home=tmp_path)
    # Trace should contain entries for each source checked, in order.
    assert r.trace
    trace = "\n".join(r.trace)
    assert "HOP3_APP" in trace
    assert ".hop3-app" in trace
    assert "hop3.toml" in trace
    # Final resolution (context default) appears because it matched.
    assert "default_app" in trace


def test_unreadable_dotfile_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unparseable hop3.toml should not crash resolution."""
    monkeypatch.delenv("HOP3_APP", raising=False)
    (tmp_path / "hop3.toml").write_text("this is not valid toml [[[ ")
    cfg = _fake_config(default_app="from-context")

    r = resolve_app(cli_app=None, config=cfg, cwd=tmp_path, home=tmp_path)
    # Falls through to context default
    assert r.app == "from-context"


def test_appresolution_dataclass_is_frozen() -> None:
    r = AppResolution(app="foo", source="test")
    with pytest.raises(FrozenInstanceError):
        r.app = "bar"  # type: ignore[misc]
