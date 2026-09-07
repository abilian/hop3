# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
`hop3 app shell` (alias `hop3 ssh`): a shell in an app's runtime context, over SSH.

The one command the CLI does not send over JSON-RPC. A terminal needs a
two-way byte stream and a pty, which the HTTP transport cannot carry, so the
CLI shells out to ``ssh -t`` against the configured ``ssh://`` server and lets
sshd own the pty, resizes and keepalives. The server side
(``hop3-server app-shell``) decides what to exec. ssh's exit status is the
shell's, and becomes ours.

Two ways in, chosen by the configured SSH user:

- ``hop3``: the key's forced command in ``~hop3/.ssh/authorized_keys``
  prepends ``hop3-server``, so the remote command is the bare
  ``app-shell <app>`` (the path ``git push`` takes).
- anyone else (root, the usual): ``su - hop3 -c "…/hop3-server app-shell
  <app>"``, the path ``hop3 login --ssh`` already uses for admin commands.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from typing import TYPE_CHECKING, NoReturn

from hop3_cli.core.ssh_target import is_safe_ssh_target
from hop3_cli.exit_codes import ExitCode

from .ssh_ops import HOP_SERVER_PATH
from .tunnel_cmd import ssh_params

if TYPE_CHECKING:
    from hop3_cli.config import Config

#: The argv prefixes the CLI intercepts instead of sending over RPC.
SHELL_COMMANDS: tuple[tuple[str, ...], ...] = (("app", "shell"), ("ssh",))

_HOP3_USER = "hop3"
# The server's app-name charset. The name lands unquoted in the SSH forced
# command's `$SSH_ORIGINAL_COMMAND`, so it must stay one shell word.
_APP_NAME_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_-]*\Z")
_CONNECT_TIMEOUT = 10
_ALIVE_INTERVAL = 15


def shell_command_args(cli_args: list[str]) -> list[str] | None:
    """The arguments after the shell command, or None if this is not one."""
    for command in SHELL_COMMANDS:
        n = len(command)
        if tuple(cli_args[:n]) == command:
            return cli_args[n:]
    return None


def intercept_app_shell(cli_args: list[str], config: Config) -> None:
    """Run `app shell` here and exit; return untouched for any other command."""
    shell_args = shell_command_args(cli_args)
    if shell_args is not None:
        handle_app_shell(shell_args, config)


def handle_app_shell(args: list[str], config: Config) -> NoReturn:
    """Open the shell over ssh and exit with the shell's status."""
    app = _app_from_args(args)
    ssh = ssh_params(config, what="`hop3 app shell`")
    target = f"{ssh['user']}@{ssh['host']}"
    if not is_safe_ssh_target(target):
        print(
            f"Refusing unsafe SSH target {target!r}: expected a plain user@host.",
            file=sys.stderr,
        )
        sys.exit(ExitCode.USAGE_ERROR)
    argv = ssh_argv(ssh, remote_shell_command(ssh["user"], app), tty=sys.stdin.isatty())
    sys.exit(subprocess.call(argv))


def remote_shell_command(ssh_user: str, app: str) -> str:
    """The command line to hand sshd, for the user we connect as."""
    if ssh_user == _HOP3_USER:
        return f"app-shell {app}"
    return f"su - {_HOP3_USER} -c {shlex.quote(f'{HOP_SERVER_PATH} app-shell {app}')}"


def ssh_argv(ssh: dict, remote_command: str, *, tty: bool) -> list[str]:
    """The exact ``ssh`` command line; a pty only when we have a terminal."""
    argv = [
        "ssh",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", f"ConnectTimeout={_CONNECT_TIMEOUT}",
        "-o", f"ServerAliveInterval={_ALIVE_INTERVAL}",
    ]  # fmt: skip
    if tty:
        argv.append("-t")
    if ssh["key"]:
        argv += ["-i", ssh["key"]]
    if ssh["port"] != 22:
        argv += ["-p", str(ssh["port"])]
    argv += [f"{ssh['user']}@{ssh['host']}", remote_command]
    return argv


def _app_from_args(args: list[str]) -> str:
    """
    The app named by the injected ``--app``; anything else is a usage error.

    The CLI has already resolved the app and injected it as ``--app NAME``
    (ADR 036 D5), so a stray token can only be a positional the user typed.
    """
    app, stray = (args[1], args[2:]) if args[:1] == ["--app"] else (None, args)
    if app is not None and not stray and _APP_NAME_RE.match(app):
        return app
    if stray:
        message = (
            "`hop3 app shell` takes no arguments; the app is named with --app. "
            f"Got: {' '.join(stray)}"
        )
    else:
        message = f"invalid app name {app!r}."
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(ExitCode.USAGE_ERROR)
