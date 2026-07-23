# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Prepare a server to run tutorial tests *on it* (a controlled environment).

Tutorials are validated by ``validoc``, which executes their bash blocks
(scaffold, build, ``hop3 deploy``, …). Running those on the dev machine has two
problems: the scaffold/build steps need every toolchain installed locally, and
the tutorial's ``hop3 deploy`` uses the dev's default CLI context — so it
deploys to whatever server that points at, not the run's target.

Running validoc on the run's server fixes both: the box already has the
installer-provisioned toolchains, and ``hop3 deploy`` targets ``localhost``.
This module installs ``validoc`` into the server venv and mints an admin token
so the on-server ``hop3`` client can authenticate to the local server.

Fails loud: without validoc or a token, on-server tutorials can't run, so we
raise rather than silently fall back to (wrong) local execution.
"""

from __future__ import annotations

import re
import shlex
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hop3_testing.targets.base import DeploymentTarget

VENV_BIN = "/home/hop3/venv/bin"

# Same shape as hop3_cli.tokens.JWT_PATTERN — a three-segment JWT.
_JWT_RE = re.compile(
    r"eyJ[A-Za-z0-9_-]{20,500}\.eyJ[A-Za-z0-9_-]{20,500}\.[A-Za-z0-9_-]{20,500}"
)

_ADMIN_USER = "tutorial-runner"
_ADMIN_EMAIL = "tutorial-runner@hop3.test"
# The password is never used to authenticate — we authenticate with the JWT the
# command returns. It only satisfies admin:create's --password-stdin.
_ADMIN_PASSWORD = "tutorial-runner"


class TutorialHostError(RuntimeError):
    """Raised when the server can't be prepared to run tutorials."""


def ensure_tutorial_host(target: DeploymentTarget) -> str:
    """
    Install validoc on the server and mint an admin token; return the token.

    Idempotent enough for the blank-slate full-suite run (the admin is created
    once on a fresh box). On a dirty box where the admin already exists,
    admin:create fails and no token is produced — we raise, surfacing why.
    """
    _configure_git_identity(target)
    _install_validoc(target)
    _patch_validoc_output_truncation(target)
    return _mint_admin_token(target)


def _configure_git_identity(target: DeploymentTarget) -> None:
    """
    Give the server a git identity so tutorials' ``git commit`` works.

    Tutorials do ``git init && git add && git commit`` to make the repo Hop3
    deploys. A fresh server has no global git user, so the commit fails with
    "Author identity unknown" — which is why this is set once, up front.
    """
    for key, value in (
        ("user.email", "tutorial-runner@hop3.test"),
        ("user.name", "Hop3 Tutorial Runner"),
    ):
        code, out, err = target.exec_run(["git", "config", "--global", key, value])
        if code != 0:
            detail = (err or out).strip()[:200]
            msg = f"Could not set git {key} on the server: {detail}"
            raise TutorialHostError(msg)


def _install_validoc(target: DeploymentTarget) -> None:
    code, out, err = target.exec_run([
        f"{VENV_BIN}/pip",
        "install",
        "--upgrade",
        "validoc",
    ])
    if code != 0:
        detail = (err or out).strip()[:300]
        msg = f"Could not install validoc on the server: {detail}"
        raise TutorialHostError(msg)


def _patch_validoc_output_truncation(target: DeploymentTarget) -> None:
    """
    STOPGAP: make validoc show the *tail* of a failed command's output.

    validoc's reporter prints only the first 10 lines of a failed step's output
    (``...split("\\n")[:10]``), but build/compile errors are at the *end*, so the
    real cause is lost. This best-effort patch rewrites those slices in the
    installed package on the test host so failures are diagnosable.

    Remove once a validoc release carries the fix upstream. Best-effort by
    design: never raises (a non-matching/renamed reporter just leaves validoc
    as-is — we don't want host prep to fail over a diagnostics nicety).
    """
    locate = f"{VENV_BIN}/python -c 'import validoc.reporter as m; print(m.__file__)'"
    code, out, _err = target.exec_run(locate)
    path = out.strip()
    if code != 0 or not path:
        return
    # Only the failure-output slices use [:10]; the success-verbose path uses
    # [:5], so this leaves it untouched.
    target.exec_run(["sed", "-i", "s/\\[:10\\]/[-80:]/g", path])


def _mint_admin_token(target: DeploymentTarget) -> str:
    # Run as the hop3 user so the DB stays hop3-owned; pipe the password to
    # --password-stdin. The su wrapper passes our stdin through to hop3-server.
    create = (
        f"{VENV_BIN}/hop3-server admin:create "
        f"{shlex.quote(_ADMIN_USER)} {shlex.quote(_ADMIN_EMAIL)} --password-stdin"
    )
    cmd = f"echo {shlex.quote(_ADMIN_PASSWORD)} | su - hop3 -c {shlex.quote(create)}"
    code, out, err = target.exec_run(cmd)

    token = _extract_jwt(out) or _extract_jwt(err)
    if not token:
        detail = (err or out).strip()[:300]
        msg = (
            f"Could not mint an admin token on the server (exit {code}). The "
            f"on-server `hop3` client can't authenticate without it: {detail}"
        )
        raise TutorialHostError(msg)
    return token


def _extract_jwt(text: str | None) -> str | None:
    match = _JWT_RE.search(text or "")
    return match.group(0) if match else None
