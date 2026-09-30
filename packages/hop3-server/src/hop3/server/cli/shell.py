# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
``hop3-server app-shell <app>``: exec an interactive shell in an app's context.

Reached over SSH. The operator's key in ``~hop3/.ssh/authorized_keys`` carries
a forced command that prepends ``hop3-server`` to whatever the client asked
for, so ``ssh -t hop3@server app-shell myapp`` lands here with a pty attached
(the path ``git push`` already takes); a client connected as root arrives
through ``su - hop3 -c``. Either way this process runs as the hop3 user and
sshd owns the pty, resizes and keepalives. This command only decides what to
exec (``hop3.run.app_env.shell_session``) and execs it, so the shell's exit
status is the session's.
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, NoReturn

from hop3.core.identifiers import InvalidIdentifierError, validate_app_name
from hop3.lib.logging import server_log
from hop3.lib.registry import register
from hop3.orm import AppRepository, get_session_factory
from hop3.run.app_env import load_artifact, make_runtime_dirs, shell_session

from ._base import Command

if TYPE_CHECKING:
    from argparse import ArgumentParser

# bash first, whatever the hop3 account's login shell says: an operator who
# hardens the account with nologin must still get a shell here.
_SHELLS = ("/bin/bash", "/bin/sh")


@register
class AppShellExecCmd(Command):
    """
    Replace this process with an interactive shell in an app's runtime context.

    Meant to be reached over SSH with a pty (``hop3 app shell`` does that);
    refuses an app that does not exist, was never deployed, or runs under
    docker-compose, rather than dropping the caller into an empty directory.

    Usage (via the SSH forced command, or as root):
        ssh -t hop3@server app-shell myapp
        su - hop3 -c "hop3-server app-shell myapp"
    """

    name = "app-shell"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("app_name", type=str, help="Name of the app")

    def run(self, app_name: str) -> None:
        try:
            validate_app_name(app_name)
        except InvalidIdentifierError as e:
            _refuse(str(e))

        session_factory = get_session_factory()
        with session_factory() as session:
            app = AppRepository(session=session).get_one_or_none(name=app_name)
            if app is None:
                _refuse(f"no app named '{app_name}'.")
            if app.runtime == "docker-compose":
                _refuse(
                    f"'{app_name}' runs under docker-compose, which "
                    "`hop3 app shell` does not cover yet."
                )
            if not app.src_path.is_dir():
                _refuse(
                    f"'{app_name}' has no source tree at {app.src_path}; "
                    "deploy it first."
                )
            make_runtime_dirs(app)
            spec = shell_session(
                app,
                load_artifact(app),
                shell=_pick_shell(),
                term=os.environ.get("TERM"),
            )

        server_log.info(
            "app shell opened",
            app_name=app_name,
            shell=spec.argv[0],
            cwd=str(spec.cwd),
            ssh_key_fingerprint=os.environ.get("FINGERPRINT", ""),
        )
        os.chdir(spec.cwd)
        os.execve(spec.argv[0], spec.argv, spec.env)


def _pick_shell() -> str:
    shell = next((s for s in _SHELLS if os.access(s, os.X_OK)), None)
    if shell is None:
        _refuse(f"no usable shell among {', '.join(_SHELLS)}.")
    return shell


def _refuse(reason: str) -> NoReturn:
    print(f"hop3-server app-shell: {reason}", file=sys.stderr)
    sys.exit(1)
