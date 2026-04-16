# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the context namespace commands (ADR 036 M2b)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from hop3_cli.commands.local.context_cmd import (
    _context_bare,
    _parse_context_use_args,
    context_rename,
    context_show,
    context_use,
)
from hop3_cli.config import Config, Context


@pytest.fixture
def tmp_config(tmp_path: Path) -> Config:
    """Config backed by a real temporary file with two contexts."""
    cfg_file = tmp_path / "config.toml"
    cfg = Config(data={}, config_file=cfg_file)
    cfg.add_context(name="dev", api_url="ssh://dev.example.com")
    cfg.add_context(name="prod", api_url="ssh://prod.example.com", protected=True)
    # Make "dev" the current context at the global level
    cfg.set_global_context("dev")
    return cfg


# ---- _parse_context_use_args ----


def test_parse_context_use_plain_name():
    name, local, glob, app = _parse_context_use_args(["prod"])
    assert (name, local, glob, app) == ("prod", False, False, None)


def test_parse_context_use_with_app_long():
    name, _, _, app = _parse_context_use_args(["--app", "myapp", "prod"])
    assert name == "prod"
    assert app == "myapp"


def test_parse_context_use_with_app_short():
    name, _, _, app = _parse_context_use_args(["-a", "myapp", "prod"])
    assert name == "prod"
    assert app == "myapp"


def test_parse_context_use_with_local_and_app():
    name, local, _, app = _parse_context_use_args(["--local", "--app", "myapp", "prod"])
    assert name == "prod"
    assert local is True
    assert app == "myapp"


# ---- context_show ----


def test_context_show_by_name(capsys, tmp_config):
    context_show(["prod"], tmp_config, MagicMock())
    out = capsys.readouterr().out
    assert "Context: prod" in out
    assert "Protected:" in out
    assert "ssh://prod.example.com" in out


def test_context_show_current_when_no_arg(capsys, tmp_config):
    context_show([], tmp_config, MagicMock())
    out = capsys.readouterr().out
    assert "Context: dev" in out
    assert "(active)" in out


def test_context_show_includes_default_app(capsys, tmp_config):
    tmp_config.set_default_app("myapp", context_name="prod")
    context_show(["prod"], tmp_config, MagicMock())
    out = capsys.readouterr().out
    assert "Default app: myapp" in out


def test_context_show_unknown_context_errors(capsys, tmp_config):
    with pytest.raises(SystemExit):
        context_show(["nonexistent"], tmp_config, MagicMock())


# ---- context_use with --app ----


def test_context_use_sets_default_app(capsys, tmp_config):
    context_use(["--app", "myapp", "prod"], tmp_config, MagicMock())
    out = capsys.readouterr().out
    assert "default app for context 'prod' to 'myapp'" in out.lower()
    # Check it was persisted
    assert tmp_config.get_default_app(context_name="prod") == "myapp"


def test_context_use_without_app_does_not_touch_default(tmp_config):
    tmp_config.set_default_app("existing", context_name="prod")
    context_use(["prod"], tmp_config, MagicMock())
    assert tmp_config.get_default_app(context_name="prod") == "existing"


# ---- context_rename ----


def test_context_rename_success(capsys, tmp_config):
    tmp_config.set_default_app("myapp", context_name="prod")
    context_rename(["prod", "production"], tmp_config, MagicMock())
    out = capsys.readouterr().out
    assert "Renamed context 'prod' -> 'production'" in out
    contexts = tmp_config.get_contexts()
    assert "prod" not in contexts
    assert "production" in contexts
    # default_app preserved
    assert tmp_config.get_default_app(context_name="production") == "myapp"


def test_context_rename_preserves_other_fields(tmp_config):
    # protected=True on prod
    context_rename(["prod", "production"], tmp_config, MagicMock())
    assert tmp_config.get_contexts()["production"].protected is True


def test_context_rename_retargets_global_current_if_needed(tmp_config):
    tmp_config.set_global_context("prod")
    context_rename(["prod", "production"], tmp_config, MagicMock())
    # global current_context should now point to the new name
    assert tmp_config.data.get("current_context") == "production"


def test_context_rename_unknown_old_fails(tmp_config):
    with pytest.raises(SystemExit):
        context_rename(["nonexistent", "new"], tmp_config, MagicMock())


def test_context_rename_collision_fails(tmp_config):
    with pytest.raises(SystemExit):
        context_rename(["prod", "dev"], tmp_config, MagicMock())


def test_context_rename_too_few_args_fails(tmp_config):
    with pytest.raises(SystemExit):
        context_rename(["prod"], tmp_config, MagicMock())


# ---- _context_bare ----


def test_context_bare_with_active_context(capsys, tmp_config):
    _context_bare(tmp_config, MagicMock())
    out = capsys.readouterr().out
    assert "Current context: dev" in out
    assert "ssh://dev.example.com" in out
    assert "(none" in out  # default_app is (none - ...)
    assert "Subcommands" in out


def test_context_bare_shows_default_app(capsys, tmp_config):
    tmp_config.set_default_app("myapp", context_name="dev")
    _context_bare(tmp_config, MagicMock())
    out = capsys.readouterr().out
    assert "Default app: myapp" in out


def test_context_bare_no_contexts(capsys, tmp_path: Path):
    cfg = Config(data={}, config_file=tmp_path / "config.toml")
    _context_bare(cfg, MagicMock())
    out = capsys.readouterr().out
    assert "No active context" in out
    assert "add" in out.lower()


def test_context_show_dataclass_field_default() -> None:
    """Sanity: Context.default_app defaults to empty string."""
    ctx = Context(name="x", api_url="")
    assert ctx.default_app == ""
