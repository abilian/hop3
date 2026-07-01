# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""hop3-deploy-server command assembly (ADR 052 D2/D3).

The credential key is threaded as --identity; the install source is emitted as
--from; and for git the branch is ALWAYS passed explicitly (regression: with the
deployer's default branch now `main`, an unspecified git branch used to fall
back to PyPI).
"""

from __future__ import annotations

from hop3_testing.targets.helpers import _build_deploy_command


def _cmd(**over):
    base = {
        "docker": False,
        "host": "203.0.113.7",
        "user": "root",
        "container_name": "c",
        "image": "i",
        "source": "local",
        "clean": False,
        "branch": "main",
        "verbose": False,
        "features": ["all"],
    }
    base.update(over)
    return _build_deploy_command(**base)


def test_identity_threaded_to_deploy():
    cmd = _cmd(ssh_key="/data/keys/k.key")
    assert cmd[cmd.index("--identity") + 1] == "/data/keys/k.key"


def test_no_key_omits_identity():
    assert "--identity" not in _cmd()


def test_docker_target_gets_no_identity():
    assert "--identity" not in _cmd(docker=True, ssh_key="/k")  # docker doesn't ssh


def test_uses_canonical_user_flag():
    assert "--user" in _cmd()
    assert "--ssh-user" not in _cmd()  # canonical spelling, not the alias


# --- source / --from ---------------------------------------------------------


def test_local_source_emits_from_local_no_branch():
    cmd = _cmd(source="local")
    assert cmd[cmd.index("--from") + 1] == "local"
    assert "--branch" not in cmd


def test_pypi_source_emits_from_pypi_no_branch():
    cmd = _cmd(source="pypi")
    assert cmd[cmd.index("--from") + 1] == "pypi"
    assert "--branch" not in cmd


def test_git_source_always_passes_branch():
    cmd = _cmd(source="git", branch="feature-x")
    assert cmd[cmd.index("--from") + 1] == "git"
    assert cmd[cmd.index("--branch") + 1] == "feature-x"


def test_git_default_branch_is_not_dropped():
    # The footgun: before the fix, branch == the (old) default was skipped, so a
    # git deploy at the default branch silently became a PyPI install. Now the
    # branch is always passed for git.
    cmd = _cmd(source="git", branch="devel")
    assert cmd[cmd.index("--from") + 1] == "git"
    assert cmd[cmd.index("--branch") + 1] == "devel"
