# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Regression: the git deployer must `git clean` the tree between deploys.

`git reset --hard` only touches tracked files, so untracked/ignored build
output (node_modules, .astro, .nuxt, dist, .next, target, vendor) from the
previous deploy survives. A redeploy then builds on top of stale state — e.g.
`astro build`/`nuxt build` over a stale node_modules fails. Every deploy must
build from the committed source.
"""

from __future__ import annotations

import contextlib
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

from hop3.deployers import git_based_deployer as gbd
from hop3.deployers.git_based_deployer import Deployer

if TYPE_CHECKING:
    from pathlib import Path


def test_git_update_cleans_working_tree(tmp_path: Path, monkeypatch) -> None:
    commands: list[str] = []

    def fake_shell(cmd, env=None, **kwargs):
        commands.append(cmd)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(gbd, "shell", fake_shell)
    monkeypatch.setattr(gbd, "chdir", lambda _p: contextlib.nullcontext())

    deployer = Deployer(app=cast("object", SimpleNamespace(src_path=tmp_path)))
    deployer._git_update("abc123")

    assert "git clean -dfx" in commands
    # Clean after the reset, and before submodules are re-synced.
    assert commands.index("git reset --hard abc123") < commands.index("git clean -dfx")
    assert commands.index("git clean -dfx") < commands.index("git submodule update")


def test_git_update_cleans_even_without_newrev(tmp_path: Path, monkeypatch) -> None:
    """No newrev (reset skipped) still cleans — reproducibility isn't optional."""
    commands: list[str] = []

    monkeypatch.setattr(
        gbd,
        "shell",
        lambda cmd, env=None, **kw: (
            commands.append(cmd) or SimpleNamespace(returncode=0)
        ),
    )
    monkeypatch.setattr(gbd, "chdir", lambda _p: contextlib.nullcontext())

    deployer = Deployer(app=cast("object", SimpleNamespace(src_path=tmp_path)))
    deployer._git_update("")

    assert "git clean -dfx" in commands
    assert not any(c.startswith("git reset") for c in commands)
