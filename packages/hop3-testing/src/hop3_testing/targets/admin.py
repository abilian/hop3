# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Admin commands on a deployed server, for the harness's own setup steps.

A few setup steps are admin-only (selecting the email catch backend, running
tutorials on the server). The admin token is minted on the server into a file
only the hop3 user and root read, and each command reads it into its
environment: it never appears on a command line, where any local user reads it
from ``/proc/<pid>/cmdline``, nor in the harness's output.

It comes from ``admin:ssh-token``, the command ``hop3 login --ssh`` runs: a
token for an active admin, and no new account. The harness used to create an
admin whose password was its own username, published in this repository, and
on a ``--host`` server that account outlived the run.
"""

from __future__ import annotations

import shlex
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from hop3_cli.commands.local.ssh_ops import HOP_SERVER_PATH, SSH_TOKEN_COMMAND

if TYPE_CHECKING:
    from .base import DeploymentTarget

VENV_BIN = str(PurePosixPath(HOP_SERVER_PATH).parent)
#: The local server, as the on-server ``hop3`` client reaches it.
LOCAL_API_URL = "http://localhost:8000"
_TOKEN_FILE = "/home/hop3/.hop3-harness-admin-token"

#: Shell words that put the admin token in a command's environment, read from
#: the token file at run time so it never appears on a command line.
ADMIN_TOKEN_ENV = f'HOP3_API_TOKEN="$(cat {_TOKEN_FILE})"'


class AdminAccessError(RuntimeError):
    """The harness could not act as an admin on the server."""


def ensure_admin_token(target: DeploymentTarget) -> None:
    """
    Mint an admin token into the token file, as the hop3 user.

    `admin:ssh-token` prints the token on a line of its own; the first JWT on
    its output is the token.
    """
    mint = (
        f"umask 077 && {SSH_TOKEN_COMMAND} "
        f"| grep -oE 'eyJ[A-Za-z0-9_.-]+' | head -1 > {_TOKEN_FILE} "
        f"&& test -s {_TOKEN_FILE}"
    )
    code, out, err = target.exec_run(f"su - hop3 -c {shlex.quote(mint)}")
    if code != 0:
        msg = f"Could not mint the harness admin token (exit {code}): {(err or out).strip()[:300]}"
        raise AdminAccessError(msg)


def run_as_admin(target: DeploymentTarget, *args: str) -> tuple[int, str, str]:
    """Run the on-server `hop3` client as the harness admin; (code, out, err)."""
    command = f"{ADMIN_TOKEN_ENV} HOP3_API_URL={LOCAL_API_URL} " + shlex.join([
        f"{VENV_BIN}/hop3",
        *args,
    ])
    return target.exec_run(f"su - hop3 -c {shlex.quote(command)}")
