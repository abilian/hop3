# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Admin commands on a deployed server, for the harness's own setup steps.

The harness deploys apps with a non-admin CLI token, and a few setup steps are
admin-only (selecting the email catch backend). The admin token is minted on
the server into a file only the hop3 user can read, and each command reads it
into its environment: it never appears on a command line, where any local user
reads it from ``/proc/<pid>/cmdline``, nor in the harness's output.
"""

from __future__ import annotations

import shlex
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import DeploymentTarget

VENV_BIN = "/home/hop3/venv/bin"
ADMIN_USER = "hop3-harness"
ADMIN_EMAIL = "hop3-harness@hop3.test"
_TOKEN_FILE = "/home/hop3/.hop3-harness-admin-token"

#: Shell words that put the admin token in a command's environment, read from
#: the token file at run time so it never appears on a command line.
ADMIN_TOKEN_ENV = f'HOP3_API_TOKEN="$(cat {_TOKEN_FILE})"'


class AdminAccessError(RuntimeError):
    """The harness could not act as an admin on the server."""


def ensure_admin_token(target: DeploymentTarget) -> None:
    """
    Create the harness admin if needed and mint its token into the token file.

    The password only satisfies `admin:create --password-stdin`; the token is
    what authenticates. `admin:token` prints it twice (the token, then a login
    example carrying it), hence the first match only.
    """
    create = (
        f"{VENV_BIN}/hop3-server admin:create {ADMIN_USER} {ADMIN_EMAIL} "
        "--password-stdin"
    )
    code, out, err = target.exec_run(
        f"echo {ADMIN_USER} | su - hop3 -c {shlex.quote(create)}"
    )
    if code != 0 and "already" not in f"{out}{err}":
        msg = f"Could not create the harness admin (exit {code}): {(err or out).strip()[:300]}"
        raise AdminAccessError(msg)

    mint = (
        f"umask 077 && {VENV_BIN}/hop3-server admin:token {ADMIN_USER} "
        f"| grep -oE 'eyJ[A-Za-z0-9_.-]+' | head -1 > {_TOKEN_FILE} "
        f"&& test -s {_TOKEN_FILE}"
    )
    code, out, err = target.exec_run(f"su - hop3 -c {shlex.quote(mint)}")
    if code != 0:
        msg = f"Could not mint the harness admin token (exit {code}): {(err or out).strip()[:300]}"
        raise AdminAccessError(msg)


def run_as_admin(target: DeploymentTarget, *args: str) -> tuple[int, str, str]:
    """Run the on-server `hop3` client as the harness admin; (code, out, err)."""
    command = f"{ADMIN_TOKEN_ENV} HOP3_API_URL=http://localhost:8000 " + shlex.join([
        f"{VENV_BIN}/hop3",
        *args,
    ])
    return target.exec_run(f"su - hop3 -c {shlex.quote(command)}")
