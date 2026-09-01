# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Entry point for the Hop3 TUI."""

from __future__ import annotations

import argparse
import importlib.metadata

from turbodesk import run

from hop3_tui.app import FOOTER_BINDINGS, TITLE, Hop3TUI, app
from hop3_tui.config import TUIConfig, get_config

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
    parser.add_argument("--token", metavar="TOKEN", help="API token for the server")
    parser.add_argument(
        "--version",
        action="version",
        version=f"hop3-tui {importlib.metadata.version('hop3-tui')}",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    config = get_config()
    if args.server or args.token:
        config = TUIConfig(**{
            **config.__dict__,
            **({"server_url": args.server} if args.server else {}),
            **({"auth_token": args.token} if args.token else {}),
        })

    hop3 = Hop3TUI(config)
    try:
        run(app(hop3), title=TITLE)
    finally:
        # An `ssh -N -L` child outliving the TUI would hold the port and confuse
        # the next run; `close` is a no-op when no tunnel was opened.
        hop3.close()


if __name__ == "__main__":
    main()
