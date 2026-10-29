# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Entry point for the Hop3 TUI."""

from __future__ import annotations

import argparse
import dataclasses
import importlib.metadata
import os
import sys
from collections.abc import Callable

from hop3_cli.commands.arguments import read_value_source
from turbodesk import run

from hop3_tui.app import FOOTER_BINDINGS, TITLE, Hop3TUI, app
from hop3_tui.config import get_config

DESCRIPTION = "Terminal interface for managing a Hop3 server."

EPILOG = """\
keys:
{keys}

configuration:
  The server and token are inherited from hop3-cli's own configuration
  (run `hop3 login` to set them up), then overridden by a TUI config file
  and finally by HOP3_SERVER_URL / HOP3_TOKEN. --server wins over all of them.
"""


def build_parser() -> argparse.ArgumentParser:
    """The command line. Kept here so `--help` needs no server and no terminal."""
    keys = "\n".join(f"  {key:<5} {label}" for key, label in FOOTER_BINDINGS)
    parser = argparse.ArgumentParser(
        prog="hop3-tui",
        description=DESCRIPTION,
        epilog=EPILOG.format(keys=keys),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--server",
        metavar="URL",
        help="Hop3 server to connect to, e.g. http://localhost:8000",
    )
    parser.add_argument(
        "--token",
        metavar="-|@PATH",
        help="API token for the server, read from stdin (-) or a file (@PATH)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"hop3-tui {importlib.metadata.version('hop3-tui')}",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    token = read_token(args.token, parser) if args.token else None
    if args.token == "-":
        reattach_terminal(parser)

    config = get_config()
    if args.server:
        config = dataclasses.replace(config, server_url=args.server)
    if token:
        config = dataclasses.replace(config, auth_token=token)

    hop3 = Hop3TUI(config)
    try:
        run(app(hop3), title=TITLE)
    finally:
        # An `ssh -N -L` child outliving the TUI would hold the port and confuse
        # the next run; `close` is a no-op when no tunnel was opened.
        hop3.close()


#: POSIX's stdin descriptor: the one the TUI's terminal reads.
STDIN_FILENO = 0


def reattach_terminal(
    parser: argparse.ArgumentParser,
    tty: str = "/dev/tty",
    dup2: Callable[[int, int], object] = os.dup2,
) -> None:
    """
    Put the controlling terminal back on stdin after ``--token -`` read it.

    The token arrives through a pipe, and the TUI then needs a terminal on
    stdin: without this, ``pass hop3 | hop3-tui --token -`` read the token
    and stopped with "needs a terminal on stdin" before drawing anything.
    """
    try:
        fd = os.open(tty, os.O_RDONLY)
    except OSError as e:
        parser.error(
            f"--token -: the token came on stdin, and the TUI then needs a "
            f"terminal, but {tty} cannot be opened ({e.strerror}). "
            "Pass the token with --token @PATH."
        )
    try:
        dup2(fd, STDIN_FILENO)
    finally:
        os.close(fd)


def read_token(source: str, parser: argparse.ArgumentParser) -> str:
    """
    The ``--token`` value from stdin (``-``) or a file (``@PATH``).

    A token on argv stays in the shell history and in `ps`. A literal still
    works, for the scripts that pass one, and says on stderr why it should go.
    """
    if source != "-" and not source.startswith("@"):
        print(
            "hop3-tui: warning: a token on the command line is kept by the shell "
            "history and visible in `ps`; pass --token - or --token @PATH.",
            file=sys.stderr,
        )
    try:
        token = read_value_source(source, label="--token").strip()
    except ValueError as e:
        parser.error(str(e))
    if not token:
        parser.error("--token: the token is empty")
    return token


if __name__ == "__main__":
    main()
