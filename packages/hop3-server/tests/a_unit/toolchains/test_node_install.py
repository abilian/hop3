# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
`install_node` provisions a pinned Node version, or fails loudly.

The Node toolchain installs `[build].node-version` into the app venv via
nodeenv. Two behaviours the deploy path depends on:

1. No pin -> use the system Node (a modern NodeSource LTS); do nothing here.
2. A pin that can't be honored (nodeenv missing) -> Abort. Previously this
   was silently ignored and the build ran on the system Node, dying deep in
   npm/pnpm with an opaque "Node too old" error (the etherpad failure mode).

Legacy construction is ``NodeToolchain("name", app_path)``.
"""

from __future__ import annotations

import pytest

from hop3.config import HopConfig
from hop3.core.env import Env
from hop3.lib import Abort
from hop3.toolchains import NodeToolchain, node as node_mod


def test_no_pin_is_a_noop(tmp_path, monkeypatch):
    # Without a pin, install_node must not touch nodeenv or the shell at all.
    def _boom(*_a, **_k):
        pytest.fail("install_node ran a shell command with no pin")

    tc = NodeToolchain("myapp", tmp_path)
    monkeypatch.setattr(tc, "shell", _boom)
    tc.install_node(Env({}))  # must not raise, must not shell out


def test_pin_without_nodeenv_aborts_loudly(tmp_path, monkeypatch):
    monkeypatch.setattr(node_mod, "check_binaries", lambda _bins: False)
    tc = NodeToolchain("myapp", tmp_path)
    with pytest.raises(Abort, match="node-version"):
        tc.install_node(Env({"NODE_VERSION": "22.13.1"}))


def test_install_modules_skips_when_node_modules_exists(tmp_path, monkeypatch):
    """
    A prebuild that already populated node_modules must not trigger a second
    toolchain npm install: the `--package-lock=false` re-resolve diverges from
    the freshly-built tree and corrupts it (nextjs @tailwindcss/oxide ENOENT,
    nuxtjs ENOTEMPTY).
    """
    src = tmp_path / "src"
    (src / "node_modules" / "left-pad").mkdir(parents=True)
    (src / "package.json").write_text("{}")

    tc = NodeToolchain("myapp", tmp_path)
    monkeypatch.setattr(node_mod, "emit", lambda *_a, **_k: None)

    def _boom(*_a, **_k):
        pytest.fail("toolchain ran npm install over an existing node_modules")

    monkeypatch.setattr(tc, "shell", _boom)
    tc.install_modules(Env({}))  # must skip, must not shell out


def test_install_modules_installs_from_the_lockfile(tmp_path, monkeypatch):
    """
    With no prebuild-populated node_modules, the toolchain installs.

    It must use `npm ci`, which installs exactly the tree recorded in the
    lockfile. `npm install` would re-resolve every semver range against the
    registry, so the same commit could ship different dependencies on a later
    deploy.
    """
    src = tmp_path / "src"
    src.mkdir(parents=True)
    (src / "package.json").write_text("{}")
    (src / "package-lock.json").write_text("{}")

    tc = NodeToolchain("myapp", tmp_path)
    monkeypatch.setattr(node_mod, "emit", lambda *_a, **_k: None)
    monkeypatch.setattr(node_mod.shutil, "which", lambda *_a, **_k: "/usr/bin/npm")
    calls: list[str] = []
    monkeypatch.setattr(tc, "shell", lambda cmd, **_k: calls.append(cmd))

    tc.install_modules(Env({}))

    assert any("npm ci" in c for c in calls)
    assert not any("--package-lock=false" in c for c in calls)


def test_install_modules_aborts_without_a_lockfile(tmp_path, monkeypatch):
    """No lockfile means unpinned dependencies — refuse rather than guess."""
    src = tmp_path / "src"
    src.mkdir(parents=True)
    (src / "package.json").write_text("{}")

    tc = NodeToolchain("myapp", tmp_path)
    monkeypatch.setattr(node_mod, "emit", lambda *_a, **_k: None)
    monkeypatch.setattr(node_mod.shutil, "which", lambda *_a, **_k: "/usr/bin/npm")
    monkeypatch.setattr(tc, "shell", lambda *_a, **_k: None)

    with pytest.raises(Abort, match=r"package-lock\.json"):
        tc.install_modules(Env({}))


def test_install_modules_finds_npm_on_the_build_path(tmp_path, monkeypatch):
    """npm from a pinned nodeenv sits in the venv, on the build PATH only."""
    src = tmp_path / "src"
    src.mkdir(parents=True)
    (src / "package.json").write_text("{}")
    (src / "package-lock.json").write_text("{}")
    venv_bin = tmp_path / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "npm").write_text("#!/bin/sh\n")
    (venv_bin / "npm").chmod(0o755)

    tc = NodeToolchain("myapp", tmp_path)
    monkeypatch.setattr(node_mod, "emit", lambda *_a, **_k: None)
    calls: list[str] = []
    monkeypatch.setattr(tc, "shell", lambda cmd, **_k: calls.append(cmd))

    tc.install_modules(Env({"PATH": str(venv_bin)}))

    assert any("npm ci" in c for c in calls)


def test_install_modules_without_npm_aborts_with_a_diagnosis(tmp_path, monkeypatch):
    """This was an `assert`, which `python -O` strips."""
    src = tmp_path / "src"
    src.mkdir(parents=True)
    (src / "package.json").write_text("{}")
    (src / "package-lock.json").write_text("{}")

    tc = NodeToolchain("myapp", tmp_path)
    monkeypatch.setattr(node_mod, "emit", lambda *_a, **_k: None)
    monkeypatch.setattr(tc, "shell", lambda *_a, **_k: None)

    with pytest.raises(Abort, match="npm is not on the build PATH"):
        tc.install_modules(Env({"PATH": str(tmp_path / "empty")}))


def test_install_modules_without_package_json_aborts_with_a_diagnosis(
    tmp_path, monkeypatch
):
    """An explicit `toolchain = "node"` skips accept(), so package.json may be absent."""
    (tmp_path / "src").mkdir(parents=True)
    tc = NodeToolchain("myapp", tmp_path)
    monkeypatch.setattr(node_mod, "emit", lambda *_a, **_k: None)

    with pytest.raises(Abort, match=r"package\.json does not exist"):
        tc.install_modules(Env({}))


def test_switching_node_under_a_running_app_aborts_with_a_diagnosis(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(node_mod, "check_binaries", lambda _bins: True)
    node = tmp_path / "venv" / "bin" / "node"
    node.parent.mkdir(parents=True)
    node.write_text("")
    enabled = tmp_path / "uwsgi-enabled"
    enabled.mkdir()
    monkeypatch.setattr(HopConfig, "UWSGI_ENABLED", property(lambda _self: enabled))
    tc = NodeToolchain("myapp", tmp_path)
    (enabled / f"{tc.app_name}_web.1.ini").write_text("")

    class _Done:
        stdout = "v20.0.0\n"

    monkeypatch.setattr(tc, "shell", lambda *_a, **_k: _Done())

    with pytest.raises(Abort, match=r"Stop the app \(hop3 app stop --app myapp\)"):
        tc.install_node(Env({"NODE_VERSION": "22.13.1"}))
