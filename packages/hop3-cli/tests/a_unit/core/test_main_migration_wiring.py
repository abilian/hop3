# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The ADR-042 one-shot migration is wired into the CLI entry point.

The autouse ``_isolate_cli_environment`` fixture (conftest.py) points
``$HOP3_CONFIG_DIR`` at ``tmp_path / "hop3-config"``, so these tests drive
``run_command_from_args`` against an isolated config dir.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import tomllib
from hop3_cli.core import credential_store as cs
from hop3_cli.main import run_command_from_args

if TYPE_CHECKING:
    from pathlib import Path


def _config_dir(tmp_path: Path) -> Path:
    # Must match the conftest's HOP3_CONFIG_DIR value.
    d = tmp_path / "hop3-config"
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_startup_migration_runs_and_drains_legacy(tmp_path: Path, capsys) -> None:
    cfgdir = _config_dir(tmp_path)
    (cfgdir / "config.toml").write_text(
        '[contexts.prod]\napi_url = "https://p"\napi_token = "T"\n'
    )
    (cfgdir / "servers.toml").write_text(
        '[servers.dev]\nurl = "https://d"\ntoken = "D"\n'
    )

    # Any local command triggers the startup migration (it runs before dispatch).
    run_command_from_args(["version"])

    # Stage 1 (r1) drained servers.toml + consolidated into config.toml; stage 2
    # (r2) drained the tokens to the store and kept the named contexts address-only
    # (so `--context prod` still selects them — ADR 042 unified model).
    assert not (cfgdir / "servers.toml").exists()
    cfg = tomllib.loads((cfgdir / "config.toml").read_text())
    # contexts kept, but address-only (no token / no api_token in config.toml).
    assert cfg["contexts"]["prod"] == {"server": "https://p"}
    assert cfg["contexts"]["dev"] == {"server": "https://d"}
    assert "token" not in cfg["contexts"]["prod"]
    assert cs.get_token("https://p") == "T"
    assert cs.get_token("https://d") == "D"
    err = capsys.readouterr().err
    assert "Migrated" in err  # stage 1 note
    assert "secret-free" in err  # stage 2 note


def test_startup_migration_is_noop_on_fresh_machine(tmp_path: Path, capsys) -> None:
    # No legacy files -> no-op: no servers.toml conjured, no migration note.
    run_command_from_args(["version"])

    assert not (tmp_path / "hop3-config" / "servers.toml").exists()
    assert "Migrated" not in capsys.readouterr().err


def test_startup_migration_names_the_unnamed_default_target(
    tmp_path: Path, capsys
) -> None:
    """
    Stage 3 runs at startup too, so no config keeps an unnamed default target.

    `[cli].default_server` resolves below every context, so leaving one in place
    means the CLI can be pointed at a server it then silently ignores.
    """
    cfgdir = _config_dir(tmp_path)
    (cfgdir / "config.toml").write_text('[cli]\ndefault_server = "ssh://root@a.com"\n')

    run_command_from_args(["version"])

    cfg = tomllib.loads((cfgdir / "config.toml").read_text())
    assert cfg["contexts"]["default"] == {"server": "ssh://root@a.com"}
    assert cfg["cli"]["default_context"] == "default"
    assert "default_server" not in cfg["cli"]
    assert "default" in capsys.readouterr().err, "the migration says what it did"
