# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for `hop3 context` — deploy environments in hop3.toml (ADR 042 r2).

The conftest autouse fixture chdir's into an isolated tmp dir, so `Path.cwd()`
is empty until a test writes a hop3.toml there.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import tomllib
from hop3_cli.commands.local.context_cmd import (
    context_add,
    context_list,
    context_remove,
    context_rename,
    context_show,
    context_use,
)


class _Cfg:
    """Minimal stand-in: context_add only reads the --app global override."""

    def __init__(self, app: str | None = None) -> None:
        self._app = app

    def get_app_override(self) -> str | None:
        return self._app


def _write_toml(text: str) -> Path:
    p = Path.cwd() / "hop3.toml"
    p.write_text(text)
    return p


def _contexts() -> dict:
    return tomllib.loads((Path.cwd() / "hop3.toml").read_text()).get("contexts", {})


# ---- add ----


def test_add_writes_block_no_secret(capsys):
    _write_toml('[metadata]\nid = "myapp"\n')
    context_add(
        ["prod", "--server", "ssh://root@prod.example.com", "--domain", "myapp.com"],
        _Cfg(),
    )
    block = _contexts()["prod"]
    assert block["server"] == "ssh://root@prod.example.com"
    assert block["domains"]["list"] == ["myapp.com"]  # unified [domains].list shape
    assert "token" not in (Path.cwd() / "hop3.toml").read_text().lower()
    out = capsys.readouterr().out
    assert "Added [contexts.prod]" in out
    assert "commit" in out.lower()


def test_add_app_from_override():
    _write_toml('[metadata]\nid = "myapp"\n')
    context_add(["prod", "--server", "ssh://root@h"], _Cfg(app="myapp-prod"))
    assert _contexts()["prod"]["app"] == "myapp-prod"


def test_add_env_pairs():
    _write_toml('[metadata]\nid = "myapp"\n')
    context_add(
        ["prod", "--server", "ssh://root@h", "--env", "LOG_LEVEL=warning"], _Cfg()
    )
    assert _contexts()["prod"]["env"] == {"LOG_LEVEL": "warning"}


def test_add_requires_server(capsys):
    _write_toml('[metadata]\nid = "myapp"\n')
    with pytest.raises(SystemExit):
        context_add(["prod"], _Cfg())
    assert "--server" in capsys.readouterr().err


def test_add_no_hop3_toml(capsys):
    with pytest.raises(SystemExit):
        context_add(["prod", "--server", "ssh://root@h"], _Cfg())
    assert "no hop3.toml" in capsys.readouterr().err.lower()


def test_add_duplicate_rejected(capsys):
    _write_toml('[metadata]\nid = "myapp"\n[contexts.prod]\nserver = "ssh://root@h"\n')
    with pytest.raises(SystemExit):
        context_add(["prod", "--server", "ssh://root@h"], _Cfg())
    assert "already exists" in capsys.readouterr().err


def test_add_invalid_name(capsys):
    _write_toml('[metadata]\nid = "myapp"\n')
    with pytest.raises(SystemExit):
        context_add(["has space", "--server", "ssh://root@h"], _Cfg())
    assert "Invalid context name" in capsys.readouterr().err


def test_add_preserves_comments():
    _write_toml('# my project\n[metadata]\nid = "myapp"  # the app\n')
    context_add(["prod", "--server", "ssh://root@h"], _Cfg())
    text = (Path.cwd() / "hop3.toml").read_text()
    assert "# my project" in text  # tomlkit round-trip keeps comments
    assert "# the app" in text


# ---- list / show ----


def test_list(capsys):
    _write_toml(
        '[metadata]\nid="myapp"\n'
        '[contexts.dev]\nserver="ssh://root@dev"\napp="myapp-dev"\n'
        '[contexts.prod]\nserver="ssh://root@prod"\n'
    )
    context_list()
    out = capsys.readouterr().out
    assert "dev" in out
    assert "prod" in out
    assert "ssh://root@dev" in out


def test_show(capsys):
    _write_toml(
        '[metadata]\nid="myapp"\n[contexts.prod]\nserver="ssh://root@prod"\napp="myapp"\n'
    )
    context_show(["prod"])
    out = capsys.readouterr().out
    assert "Context: prod" in out
    assert "ssh://root@prod" in out


def test_show_unknown(capsys):
    _write_toml('[metadata]\nid="myapp"\n')
    with pytest.raises(SystemExit):
        context_show(["nope"])
    assert "not found" in capsys.readouterr().err


# ---- remove / rename ----


def test_remove(capsys):
    _write_toml('[metadata]\nid="myapp"\n[contexts.prod]\nserver="ssh://root@h"\n')
    context_remove(["prod"])
    assert "prod" not in _contexts()
    assert "Removed" in capsys.readouterr().out


def test_rename(capsys):
    _write_toml(
        '[metadata]\nid="myapp"\n[contexts.old]\nserver="ssh://root@h"\napp="a"\n'
    )
    context_rename(["old", "new"])
    ctxs = _contexts()
    assert "old" not in ctxs
    assert ctxs["new"] == {"server": "ssh://root@h", "app": "a"}


# ---- use (writes the gitignored per-checkout pin) ----


def test_use_writes_overlay(capsys):
    _write_toml('[metadata]\nid="myapp"\n[contexts.dev]\nserver="ssh://root@dev"\n')
    context_use(["dev"])
    overlay = tomllib.loads((Path.cwd() / ".hop3-local.toml").read_text())
    assert overlay["local"]["context"] == "dev"  # ADR 042 r2 renamed [current]->[local]
    out = capsys.readouterr().out
    assert "not committed" in out.lower()


def test_use_unknown_context(capsys):
    _write_toml('[metadata]\nid="myapp"\n[contexts.dev]\nserver="ssh://root@dev"\n')
    with pytest.raises(SystemExit):
        context_use(["nope"])
    assert "not found" in capsys.readouterr().err


def test_use_rejects_global(capsys):
    _write_toml('[metadata]\nid="myapp"\n[contexts.dev]\nserver="ssh://root@dev"\n')
    with pytest.raises(SystemExit):
        context_use(["dev", "--global"])
    assert "retired" in capsys.readouterr().err
