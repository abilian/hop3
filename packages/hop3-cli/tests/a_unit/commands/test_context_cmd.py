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
from hop3_cli.config import Config


def _cfg(app: str | None = None) -> Config:
    """A real Config rooted in the isolated cwd (so global writes/saves work)."""
    config = Config(data={}, config_file=Path.cwd() / "config.toml")
    config.set_app_override(app)
    return config


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
        _cfg(),
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
    context_add(["prod", "--server", "ssh://root@h"], _cfg(app="myapp-prod"))
    assert _contexts()["prod"]["app"] == "myapp-prod"


def test_add_env_pairs():
    _write_toml('[metadata]\nid = "myapp"\n')
    context_add(
        ["prod", "--server", "ssh://root@h", "--env", "LOG_LEVEL=warning"], _cfg()
    )
    assert _contexts()["prod"]["env"] == {"LOG_LEVEL": "warning"}


def test_add_requires_server(capsys):
    _write_toml('[metadata]\nid = "myapp"\n')
    with pytest.raises(SystemExit):
        context_add(["prod"], _cfg())
    assert "--server" in capsys.readouterr().err


def test_add_global_when_no_project(capsys):
    # No hop3.toml here: `context add` defines a GLOBAL context (named server)
    # so `hop3 apps --context prod` works project-lessly. (ADR 042 unified model.)
    config = _cfg()
    context_add(["prod", "--server", "ssh://root@h"], config)
    assert config.get_context_server("prod") == "ssh://root@h"
    assert not (Path.cwd() / "hop3.toml").exists()  # nothing written to a project file
    out = capsys.readouterr().out
    assert "global context 'prod'" in out
    assert "--context prod" in out


def test_add_global_rejects_project_only_fields(capsys):
    # A global context is just a named server; project-only fields must not be
    # silently dropped — they error.
    with pytest.raises(SystemExit):
        context_add(["prod", "--server", "ssh://root@h", "--domain", "x.com"], _cfg())
    assert "global context" in capsys.readouterr().err


def test_add_force_global_inside_project(capsys):
    # --global writes config.toml even when a project hop3.toml is present.
    _write_toml('[metadata]\nid = "myapp"\n')
    config = _cfg()
    context_add(["prod", "--server", "ssh://root@h", "--global"], config)
    assert config.get_context_server("prod") == "ssh://root@h"
    assert "prod" not in _contexts()  # not written to the project file


def test_add_duplicate_rejected(capsys):
    _write_toml('[metadata]\nid = "myapp"\n[contexts.prod]\nserver = "ssh://root@h"\n')
    with pytest.raises(SystemExit):
        context_add(["prod", "--server", "ssh://root@h"], _cfg())
    assert "already exists" in capsys.readouterr().err


def test_add_invalid_name(capsys):
    _write_toml('[metadata]\nid = "myapp"\n')
    with pytest.raises(SystemExit):
        context_add(["has space", "--server", "ssh://root@h"], _cfg())
    assert "Invalid context name" in capsys.readouterr().err


def test_add_preserves_comments():
    _write_toml('# my project\n[metadata]\nid = "myapp"  # the app\n')
    context_add(["prod", "--server", "ssh://root@h"], _cfg())
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
    context_list(_cfg())
    out = capsys.readouterr().out
    assert "dev" in out
    assert "prod" in out
    assert "ssh://root@dev" in out


def test_show(capsys):
    _write_toml(
        '[metadata]\nid="myapp"\n[contexts.prod]\nserver="ssh://root@prod"\napp="myapp"\n'
    )
    context_show(["prod"], _cfg())
    out = capsys.readouterr().out
    assert "Context: prod" in out
    assert "ssh://root@prod" in out


def test_show_unknown(capsys):
    _write_toml('[metadata]\nid="myapp"\n')
    with pytest.raises(SystemExit):
        context_show(["nope"], _cfg())
    assert "not found" in capsys.readouterr().err


# ---- remove / rename ----


def test_remove(capsys):
    _write_toml('[metadata]\nid="myapp"\n[contexts.prod]\nserver="ssh://root@h"\n')
    context_remove(["prod"], _cfg())
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
    context_use(["dev"], _cfg())
    overlay = tomllib.loads((Path.cwd() / ".hop3-local.toml").read_text())
    assert overlay["local"]["context"] == "dev"  # ADR 042 r2 renamed [current]->[local]
    out = capsys.readouterr().out
    assert "not committed" in out.lower()


def test_use_unknown_context(capsys):
    _write_toml('[metadata]\nid="myapp"\n[contexts.dev]\nserver="ssh://root@dev"\n')
    with pytest.raises(SystemExit):
        context_use(["nope"], _cfg())
    assert "not found" in capsys.readouterr().err


def test_use_rejects_global(capsys):
    _write_toml('[metadata]\nid="myapp"\n[contexts.dev]\nserver="ssh://root@dev"\n')
    with pytest.raises(SystemExit):
        context_use(["dev", "--global"], _cfg())
    assert "no global form" in capsys.readouterr().err


def test_use_global_context_name_redirects(capsys):
    """A name that exists only as a GLOBAL context must not dead-end on the
    project file — it names the global context and points at the right
    mechanism (regression for the misleading 'not found in <cwd>/hop3.toml')."""
    _write_toml('[metadata]\nid="myapp"\n[contexts.dev]\nserver="ssh://root@dev"\n')
    config = _cfg()
    config.set_context_server("prod", "ssh://root@prod")  # global, not in project
    with pytest.raises(SystemExit) as exc:
        context_use(["prod"], config)
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "global context" in err
    assert "--context prod" in err


# ---- global contexts (project-less) ----


def test_list_global_when_no_project(capsys):
    config = _cfg()
    config.set_context_server("prod", "ssh://root@prod")
    config.set_context_server("dev", "ssh://root@dev")
    config.set_default_context("prod")
    context_list(config)
    out = capsys.readouterr().out
    assert "Global contexts" in out
    assert "ssh://root@prod" in out
    assert "Default context: prod" in out


def test_show_global_when_no_project(capsys):
    config = _cfg()
    config.set_context_server("prod", "ssh://root@prod")
    context_show(["prod"], config)
    out = capsys.readouterr().out
    assert "[global]" in out
    assert "ssh://root@prod" in out


def test_remove_global_when_no_project(capsys):
    config = _cfg()
    config.set_context_server("prod", "ssh://root@prod")
    context_remove(["prod"], config)
    assert config.get_context_server("prod") is None
    assert "Removed global context" in capsys.readouterr().out
