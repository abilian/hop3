# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the `hop3 server` verbs (ADR 042 Step 4)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from hop3_cli.commands.local.server_cmd import handle_server
from hop3_cli.core.server_registry import (
    ServerRecord,
    ServerRegistry,
    load_registry,
    save_registry,
)

if TYPE_CHECKING:
    from pathlib import Path


# ---- Fixtures -------------------------------------------------------------


def _config_with_data(data: dict | None = None) -> MagicMock:
    """A Config-like mock whose .data is the supplied dict."""
    cfg = MagicMock()
    cfg.data = data if data is not None else {}
    cfg.config_file = None
    return cfg


def _printer() -> MagicMock:
    return MagicMock()


@pytest.fixture(autouse=True)
def redirect_servers_path(tmp_path, monkeypatch):
    """Point all CLI state files at tmp_path so tests stay isolated."""
    servers_toml = tmp_path / "servers.toml"
    state_toml = tmp_path / "state.toml"
    monkeypatch.setattr(
        "hop3_cli.core.server_registry.default_servers_path",
        lambda: servers_toml,
    )
    monkeypatch.setattr(
        "hop3_cli.core.cli_state.default_state_path",
        lambda: state_toml,
    )
    monkeypatch.setattr(
        "hop3_cli.commands.local.server_cmd._legacy_config_path",
        lambda: tmp_path / "config.toml",
    )
    return servers_toml


# ---- list ----------------------------------------------------------------


def test_server_list_empty(capsys: pytest.CaptureFixture[str]) -> None:
    handle_server(["list"], _config_with_data(), _printer())
    out = capsys.readouterr().out
    assert "No servers registered." in out
    assert "hop3 server add" in out


def test_server_list_shows_records(
    redirect_servers_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save_registry(
        ServerRegistry(
            path=redirect_servers_path,
            records={
                "dev": ServerRecord(name="dev", url="https://dev.example.com"),
                "prod": ServerRecord(
                    name="prod",
                    url="https://prod.example.com",
                    protected=True,
                ),
            },
        )
    )
    handle_server(["list"], _config_with_data(), _printer())
    out = capsys.readouterr().out
    assert "dev" in out
    assert "prod" in out
    assert "https://dev.example.com" in out
    assert "Protected:   yes" in out


# ---- add ----------------------------------------------------------------


def test_server_add_writes_record(
    redirect_servers_path: Path,
) -> None:
    handle_server(
        ["add", "dev", "--url", "https://dev.example.com", "--token", "tok-1"],
        _config_with_data(),
        _printer(),
    )
    registry = load_registry(redirect_servers_path)
    rec = registry.get("dev")
    assert rec is not None
    assert rec.url == "https://dev.example.com"
    assert rec.token == "tok-1"


def test_server_add_rejects_invalid_name(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Same naming rules as project contexts — reserved names rejected."""
    with pytest.raises(SystemExit):
        handle_server(
            ["add", "default", "--url", "https://example.com"],
            _config_with_data(),
            _printer(),
        )
    assert "reserved" in capsys.readouterr().err.lower()


def test_server_add_requires_url(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        handle_server(["add", "dev"], _config_with_data(), _printer())
    assert "--url is required" in capsys.readouterr().err


def test_server_add_rejects_duplicate(
    redirect_servers_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    save_registry(
        ServerRegistry(
            path=redirect_servers_path,
            records={"dev": ServerRecord(name="dev", url="x")},
        )
    )
    with pytest.raises(SystemExit):
        handle_server(
            ["add", "dev", "--url", "y"],
            _config_with_data(),
            _printer(),
        )
    assert "already exists" in capsys.readouterr().err


def test_server_add_protected_flag(
    redirect_servers_path: Path,
) -> None:
    handle_server(
        [
            "add",
            "prod",
            "--url",
            "https://prod.example.com",
            "--protected",
        ],
        _config_with_data(),
        _printer(),
    )
    registry = load_registry(redirect_servers_path)
    assert registry.get("prod").protected is True


def test_server_add_ssh_port_integer(redirect_servers_path: Path) -> None:
    handle_server(
        [
            "add",
            "dev",
            "--url",
            "https://dev.example.com",
            "--ssh-port",
            "2222",
        ],
        _config_with_data(),
        _printer(),
    )
    registry = load_registry(redirect_servers_path)
    assert registry.get("dev").ssh_port == 2222


def test_server_add_ssh_port_non_integer(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        handle_server(
            [
                "add",
                "dev",
                "--url",
                "https://dev.example.com",
                "--ssh-port",
                "not-an-int",
            ],
            _config_with_data(),
            _printer(),
        )
    err = capsys.readouterr().err
    assert "ssh-port" in err


# ---- remove --------------------------------------------------------------


def test_server_remove_drops_record(
    redirect_servers_path: Path,
) -> None:
    save_registry(
        ServerRegistry(
            path=redirect_servers_path,
            records={"dev": ServerRecord(name="dev", url="x")},
        )
    )
    handle_server(["remove", "dev"], _config_with_data(), _printer())
    registry = load_registry(redirect_servers_path)
    assert registry.get("dev") is None


def test_server_remove_unknown_exits(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        handle_server(["remove", "nope"], _config_with_data(), _printer())
    assert "not found" in capsys.readouterr().err


def test_server_remove_warns_when_was_default(
    redirect_servers_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from hop3_cli.core.cli_state import (  # noqa: PLC0415
        get_current_server,
        set_current_server,
    )

    save_registry(
        ServerRegistry(
            path=redirect_servers_path,
            records={"dev": ServerRecord(name="dev", url="x")},
        )
    )
    set_current_server("dev")
    handle_server(["remove", "dev"], _config_with_data(), _printer())
    err = capsys.readouterr().err
    assert "global default" in err
    # Dangling pointer cleaned up (should-fix: was leaving a stale pointer).
    assert get_current_server() is None


# ---- show ----------------------------------------------------------------


def test_server_show_existing(
    redirect_servers_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save_registry(
        ServerRegistry(
            path=redirect_servers_path,
            records={
                "dev": ServerRecord(
                    name="dev",
                    url="https://dev.example.com",
                    default_app="myapp",
                    protected=True,
                ),
            },
        )
    )
    handle_server(["show", "dev"], _config_with_data(), _printer())
    out = capsys.readouterr().out
    assert "https://dev.example.com" in out
    assert "Default app: myapp" in out
    assert "Protected:   yes" in out


def test_server_show_unknown(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        handle_server(["show", "nope"], _config_with_data(), _printer())
    assert "not found" in capsys.readouterr().err


def test_server_show_marks_global_default(
    redirect_servers_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from hop3_cli.core.cli_state import set_current_server  # noqa: PLC0415

    save_registry(
        ServerRegistry(
            path=redirect_servers_path,
            records={"dev": ServerRecord(name="dev", url="x")},
        )
    )
    set_current_server("dev")
    handle_server(["show", "dev"], _config_with_data(), _printer())
    out = capsys.readouterr().out
    assert "global default" in out


# ---- use -----------------------------------------------------------------


def test_server_use_sets_global_default(
    redirect_servers_path: Path,
) -> None:
    """ADR 042: the global-default pointer lives in state.toml, not config.toml."""
    from hop3_cli.core.cli_state import get_current_server  # noqa: PLC0415

    save_registry(
        ServerRegistry(
            path=redirect_servers_path,
            records={"dev": ServerRecord(name="dev", url="x")},
        )
    )
    cfg = _config_with_data({})
    handle_server(["use", "dev"], cfg, _printer())
    # The pointer lives in state.toml (not config.toml).
    assert get_current_server() == "dev"
    cfg.save.assert_not_called()


def test_server_use_rejects_unknown(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        handle_server(["use", "nope"], _config_with_data(), _printer())
    assert "not found" in capsys.readouterr().err


def test_server_use_default_app_sets_field(
    redirect_servers_path: Path,
) -> None:
    """ADR 042 app-resolution source #8: server.default_app."""
    from hop3_cli.core.cli_state import set_current_server  # noqa: PLC0415

    save_registry(
        ServerRegistry(
            path=redirect_servers_path,
            records={"dev": ServerRecord(name="dev", url="x")},
        )
    )
    set_current_server("dev")
    handle_server(
        ["use", "--default-app", "myapp"],
        _config_with_data({}),
        _printer(),
    )
    registry = load_registry(redirect_servers_path)
    assert registry.get("dev").default_app == "myapp"


def test_server_use_default_app_without_current_server(
    redirect_servers_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--default-app needs a current server first."""
    with pytest.raises(SystemExit):
        handle_server(
            ["use", "--default-app", "myapp"],
            _config_with_data({}),
            _printer(),
        )
    assert "No global default server" in capsys.readouterr().err


# ---- login --------------------------------------------------------------


def test_server_login_rotates_token(redirect_servers_path: Path) -> None:
    save_registry(
        ServerRegistry(
            path=redirect_servers_path,
            records={
                "dev": ServerRecord(name="dev", url="x", token="old"),
            },
        )
    )
    handle_server(
        ["login", "dev", "--token", "new-tok"],
        _config_with_data(),
        _printer(),
    )
    registry = load_registry(redirect_servers_path)
    assert registry.get("dev").token == "new-tok"


def test_server_login_unknown(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        handle_server(
            ["login", "nope", "--token", "x"],
            _config_with_data(),
            _printer(),
        )
    assert "not found" in capsys.readouterr().err


def test_use_default_app_resolves_through_source_8(
    redirect_servers_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Blocker regression: ``hop3 server use --default-app foo`` writes to
    servers.toml AND the resolver actually reads it back as app source #8.

    Without this end-to-end test, the verb could appear to work while
    the resolver still consults the empty legacy config.toml location.
    """
    from hop3_cli.core.cli_state import set_current_server  # noqa: PLC0415
    from hop3_cli.core.resolution import resolve_app  # noqa: PLC0415

    # Register a server, set it as the global default, give it a
    # default_app via the new verb path.
    save_registry(
        ServerRegistry(
            path=redirect_servers_path,
            records={"dev": ServerRecord(name="dev", url="https://dev.example.com")},
        )
    )
    set_current_server("dev")
    handle_server(
        ["use", "--default-app", "myapp"],
        _config_with_data({}),
        _printer(),
    )

    # Now drive resolve_app: nothing else resolves, so source #8 must win.
    monkeypatch.delenv("HOP3_APP", raising=False)
    cfg = MagicMock()
    cfg.get_current_context_name.return_value = "dev"
    cfg.data = {}  # No legacy contexts in-memory
    resolution = resolve_app(
        cli_app=None,
        config=cfg,
        cwd=redirect_servers_path.parent,  # No hop3.toml here
        home=redirect_servers_path.parent,
    )
    assert resolution.app == "myapp", (
        "source #8 must read default_app from servers.toml"
    )


def test_server_login_requires_token(
    redirect_servers_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save_registry(
        ServerRegistry(
            path=redirect_servers_path,
            records={"dev": ServerRecord(name="dev", url="x")},
        )
    )
    with pytest.raises(SystemExit):
        handle_server(["login", "dev"], _config_with_data(), _printer())
    assert "--token is required" in capsys.readouterr().err


# ---- lazy migration ----------------------------------------------------


def test_lazy_migration_on_first_call(
    redirect_servers_path: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """First `hop3 server` call migrates legacy config.toml records.

    Conditions: servers.toml doesn't exist yet, config.toml has
    [contexts.*] records. After the call: servers.toml exists,
    config.toml renamed to .bak, stderr summary printed.
    """
    legacy_path = tmp_path / "config.toml"
    legacy_path.write_text(
        """
[contexts.prod]
api_url = "https://prod.example.com"
api_token = "tok-1"
"""
    )
    cfg = MagicMock()
    cfg.data = {
        "contexts": {
            "prod": {"api_url": "https://prod.example.com", "api_token": "tok-1"}
        }
    }
    cfg.config_file = legacy_path

    handle_server(["list"], cfg, _printer())
    # servers.toml created.
    assert redirect_servers_path.is_file()
    # Legacy config.toml renamed to .bak.
    assert not legacy_path.exists()
    assert (tmp_path / "config.toml.pre-042.bak").is_file()
    # Migration summary in stderr.
    err = capsys.readouterr().err
    assert "Migrated" in err
    assert "prod" in err


def test_no_migration_when_already_migrated(
    redirect_servers_path: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When servers.toml already exists, migration doesn't re-run."""
    save_registry(
        ServerRegistry(
            path=redirect_servers_path,
            records={"dev": ServerRecord(name="dev", url="x")},
        )
    )
    # Legacy file with different records — shouldn't be touched.
    legacy_path = tmp_path / "config.toml"
    legacy_path.write_text('[contexts.other]\napi_url = "y"\n')
    cfg = MagicMock()
    cfg.data = {"contexts": {"other": {"api_url": "y"}}}
    cfg.config_file = legacy_path

    handle_server(["list"], cfg, _printer())
    # Legacy file NOT renamed.
    assert legacy_path.is_file()
    # 'Migrated' message NOT emitted.
    assert "Migrated" not in capsys.readouterr().err
