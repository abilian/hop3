# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""ensure_tutorial_host: install validoc + mint an admin token on the server."""

from __future__ import annotations

import pytest
from hop3_testing.system_tests.tutorial_host import (
    TutorialHostError,
    ensure_tutorial_host,
)

# A syntactically valid three-segment JWT (matches the extractor's pattern).
_TOKEN = "eyJ" + "a" * 30 + ".eyJ" + "b" * 30 + "." + "c" * 30


class _FakeTarget:
    """
    Records exec_run commands; succeeds by default, with optional scripting.

    Robust to added prep steps: a command containing ``fail_substr`` returns a
    failure; an ``admin:create`` returns ``token_out``; everything else is a
    clean success. This decouples the tests from the exact number/order of
    best-effort steps (git config, validoc patch, …).
    """

    def __init__(self, *, token_out: str | None = None, fail_substr: str | None = None):
        self.calls: list = []
        self._token_out = token_out
        self._fail_substr = fail_substr

    def exec_run(self, cmd):
        self.calls.append(cmd)
        text = cmd if isinstance(cmd, str) else " ".join(cmd)
        if self._fail_substr and self._fail_substr in text:
            return (1, "", f"failed: {self._fail_substr}")
        if "admin:create" in text and self._token_out:
            return (0, self._token_out, "")
        return (0, "", "")


def test_configures_git_installs_validoc_and_mints_token():
    target = _FakeTarget(token_out=f"Admin created. Token: {_TOKEN}")

    token = ensure_tutorial_host(target)

    assert token == _TOKEN
    joined = [c if isinstance(c, str) else " ".join(c) for c in target.calls]
    # git identity set (tutorials git-commit before deploy)
    assert any("git config --global user.email" in c for c in joined)
    # validoc installed into the server venv
    assert any("/home/hop3/venv/bin/pip" in c and "validoc" in c for c in joined)
    # token minted via admin:create, run as the hop3 user, password on stdin
    assert any(
        "admin:create" in c and "--password-stdin" in c and "su - hop3" in c
        for c in joined
    )


def test_raises_when_git_config_fails():
    target = _FakeTarget(fail_substr="git config")
    with pytest.raises(TutorialHostError, match="git"):
        ensure_tutorial_host(target)


def test_raises_when_validoc_install_fails():
    target = _FakeTarget(fail_substr="pip install")
    with pytest.raises(TutorialHostError, match="validoc"):
        ensure_tutorial_host(target)


def test_raises_when_no_token_minted():
    # admin already exists on a dirty box: no token in the output -> loud failure,
    # never a silent return that would leave the client unauthenticated.
    target = _FakeTarget(token_out=None)
    with pytest.raises(TutorialHostError, match="token"):
        ensure_tutorial_host(target)
