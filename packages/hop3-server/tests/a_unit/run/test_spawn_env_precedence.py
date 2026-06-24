# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""A persisted [env] must never clobber a toolchain-owned absolute path.

The demo59 crash-loop: its hop3.toml hardcoded MIX_HOME=…/demo59/.mix, which the
DB-persisted [env] then applied at runtime *over* the Elixir toolchain's correct
app-local MIX_HOME. `mix run` then found a .mix with no Hex installed and fell
back to the interactive 'Shall I install Hex?' prompt. spawn.py now protects the
build artifact's runtime env_vars (the toolchain-owned keys) from [env] override.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from hop3.core.artifacts import BuildArtifact, RuntimeConfig
from hop3.core.env import Env
from hop3.run.spawn import AppLauncher


def _launcher(*, artifact_env: dict, db_env: dict) -> AppLauncher:
    """An AppLauncher seeded only with what make_env() reads."""
    launcher = AppLauncher.__new__(AppLauncher)
    launcher.app_name = "myapp"
    launcher.app_path = Path("/home/hop3/apps/myapp")
    launcher.virtualenv_path = Path("/home/hop3/apps/myapp/venv")
    launcher.artifact = BuildArtifact(
        kind="elixir",
        runtime=RuntimeConfig(env_vars=dict(artifact_env)),
    )
    launcher.app = SimpleNamespace(
        name="myapp",
        port=12345,  # set so make_env reuses it instead of get_free_port()
        get_runtime_env=lambda: Env(dict(db_env)),
    )
    return launcher


def test_toolchain_env_not_clobbered_by_stale_db_env() -> None:
    launcher = _launcher(
        artifact_env={
            "MIX_HOME": "/home/hop3/apps/myapp/.mix",
            "HEX_HOME": "/home/hop3/apps/myapp/.hex",
        },
        db_env={
            "MIX_HOME": "/home/hop3/apps/demo59/.mix",  # stale, hardcoded
            "DATABASE_URL": "postgres://localhost/myapp",  # legit, not toolchain-owned
        },
    )
    env = launcher.make_env()

    # The toolchain's app-local paths win over the stale [env] values.
    assert env["MIX_HOME"] == "/home/hop3/apps/myapp/.mix"
    assert env["HEX_HOME"] == "/home/hop3/apps/myapp/.hex"
    # Keys the toolchain does NOT own are still applied from [env].
    assert env["DATABASE_URL"] == "postgres://localhost/myapp"


def test_db_env_still_applies_for_non_toolchain_keys() -> None:
    launcher = _launcher(
        artifact_env={"MIX_HOME": "/home/hop3/apps/myapp/.mix"},
        db_env={"API_KEY": "secret", "DEBUG": "true"},
    )
    env = launcher.make_env()

    assert env["MIX_HOME"] == "/home/hop3/apps/myapp/.mix"
    assert env["API_KEY"] == "secret"
    assert env["DEBUG"] == "true"
