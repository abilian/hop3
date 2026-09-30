# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The runtime context of an app, for a process that is not the app.

``hop3 run`` and ``hop3 app shell`` both start a process inside an app: its
working tree, the environment its workers see, its toolchain on ``PATH``. This
module is the one place that decides what that context is, so the two commands
cannot drift, and so a later transport (a browser terminal) reuses the decision
rather than the pipe.

Every environment here is built from scratch. The server's own environment
(``HOP3_SECRET_KEY``, the database URL, the SSH forced command's
``FINGERPRINT``) never reaches the child; ``PATH`` is the one value borrowed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from hop3.config import HOP3_USER
from hop3.core.artifacts import ARTIFACT_FILENAME, BuildArtifact

if TYPE_CHECKING:
    from collections.abc import MutableMapping

    from hop3.core.artifacts import RuntimeConfig
    from hop3.orm import App


@dataclass(frozen=True, slots=True)
class ShellSession:
    """What to exec for an interactive shell in an app: argv, cwd and env."""

    argv: tuple[str, ...]
    cwd: Path
    env: dict[str, str]


def load_artifact(app: App) -> BuildArtifact | None:
    """The app's build artifact, or None when it was never built."""
    return BuildArtifact.load(app.app_path / ARTIFACT_FILENAME)


def build_app_env(
    app: App, artifact: BuildArtifact | None, *, cwd: Path | None = None
) -> dict[str, str]:
    """
    The environment of a process in ``app``'s runtime context.

    The core that ``AppLauncher.make_env`` gives the app's own workers and that
    ``hop3 run`` and ``hop3 app shell`` give a one-off process: the bootstrap
    (identity, the virtualenv first on ``PATH``), the toolchain's env and
    ``PATH`` entries from the build artifact, then the persisted ``[env]``
    block, which never overrides a toolchain-owned key. What only a worker
    needs (port allocation, proxy defaults) stays in ``make_env``.

    ``HOME`` and ``TMPDIR`` are the app's own. With the control plane's home,
    every app shared one ``~/.ssh`` and one set of caches: Gitea and Forgejo
    rewrote the ``authorized_keys`` that holds Hop3's git-push keys.
    """
    venv_bin = app.virtualenv_path / "bin"
    env = {
        "APP": app.name,
        "HOME": str(app.home_path),
        "TMPDIR": str(app.tmp_path),
        "USER": HOP3_USER,
        "PATH": f"{venv_bin}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        "PWD": str(cwd or app.src_path),
        "VIRTUAL_ENV": str(app.virtualenv_path),
    }
    toolchain_keys: set[str] = set()
    if artifact is not None:
        apply_artifact_runtime(env, artifact.runtime)
        toolchain_keys = set(artifact.runtime.env_vars)
    persisted = app.get_runtime_env().items()
    env.update({k: v for k, v in persisted if k not in toolchain_keys})
    if app.port:
        env.setdefault("PORT", str(app.port))
    return env


def make_runtime_dirs(app: App) -> None:
    """Create the HOME and TMPDIR ``build_app_env`` names, before a process
    starts in them."""
    app.home_path.mkdir(exist_ok=True)
    app.tmp_path.mkdir(exist_ok=True)


def apply_artifact_runtime(
    env: MutableMapping[str, str], runtime: RuntimeConfig
) -> None:
    """
    The toolchain's contribution: its env vars, never over a key already set,
    and its ``PATH`` entries in front (a Nix runtime's store binaries, a
    toolchain's own bin directory).
    """
    for key, value in runtime.env_vars.items():
        env.setdefault(key, value)
    for path in runtime.path_prepend:
        if path and path not in env["PATH"].split(":"):
            env["PATH"] = f"{path}:{env['PATH']}"


def shell_session(
    app: App,
    artifact: BuildArtifact | None,
    *,
    shell: str,
    term: str | None,
) -> ShellSession:
    """
    The shell to start for ``app``: a decision, no I/O.

    ``cwd`` is the artifact's working directory when the toolchain declared one
    (a Nix runtime runs from its store path), else the source tree. ``env`` is
    ``build_app_env`` plus what a terminal needs: the client's ``TERM``, a
    prompt that names the app, and no shared history file. bash starts with
    ``--norc`` so the ``hop3`` user's rc files cannot rewrite ``PATH`` under
    the toolchain.
    """
    working_dir = artifact.runtime.working_dir if artifact is not None else ""
    cwd = Path(working_dir) if working_dir else app.src_path
    env = build_app_env(app, artifact)
    env["PWD"] = str(cwd)
    if term:
        env["TERM"] = term
    env["PS1"] = f"[{app.name}] \\w$ "
    env["HISTFILE"] = ""
    argv = (shell, "--norc") if Path(shell).name == "bash" else (shell,)
    return ShellSession(argv=argv, cwd=cwd, env=env)
