# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""ensure_tutorial_host: install validoc + mint the admin token file on the server."""

from __future__ import annotations

import pytest
from hop3_testing.system_tests.tutorial_host import (
    TutorialHostError,
    ensure_tutorial_host,
)


class _FakeTarget:
    """
    Records exec_run commands; succeeds by default, with optional scripting.

    Robust to added prep steps: a command containing ``fail_substr`` returns a
    failure; everything else is a clean success. This decouples the tests from
    the exact number/order of best-effort steps (git config, validoc patch, …).
    """

    def __init__(self, *, fail_substr: str | None = None):
        self.calls: list = []
        self._fail_substr = fail_substr

    def exec_run(self, cmd):
        self.calls.append(cmd)
        text = cmd if isinstance(cmd, str) else " ".join(cmd)
        if self._fail_substr and self._fail_substr in text:
            return (1, "", f"failed: {self._fail_substr}")
        return (0, "", "")


def test_configures_git_installs_validoc_and_mints_the_token_file():
    target = _FakeTarget()

    ensure_tutorial_host(target)

    joined = [c if isinstance(c, str) else " ".join(c) for c in target.calls]
    # git identity set (tutorials git-commit before deploy)
    assert any("git config --global user.email" in c for c in joined)
    # validoc installed into the server venv
    assert any("/home/hop3/venv/bin/pip" in c and "validoc" in c for c in joined)
    # and uv, which a tutorial runs on the "reader's machine" (the server)
    assert any("/home/hop3/venv/bin/pip" in c and " uv" in c for c in joined)
    # the token is minted into a 0600 file on the server, as the hop3 user
    assert any("admin:token" in c and "umask 077" in c for c in joined)


def test_raises_when_git_config_fails():
    target = _FakeTarget(fail_substr="git config")
    with pytest.raises(TutorialHostError, match="git"):
        ensure_tutorial_host(target)


def test_raises_when_validoc_install_fails():
    target = _FakeTarget(fail_substr="pip install")
    with pytest.raises(TutorialHostError, match="validoc"):
        ensure_tutorial_host(target)


def test_raises_when_the_token_cannot_be_minted():
    # Without the token the on-server client cannot authenticate: a loud
    # failure, never a silent return.
    target = _FakeTarget(fail_substr="admin:token")
    with pytest.raises(TutorialHostError, match="token"):
        ensure_tutorial_host(target)
