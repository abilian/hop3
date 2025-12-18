# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Command-line interface for demo launcher."""

from __future__ import annotations

import argparse
import textwrap
from pathlib import Path

from lib.discovery import discover_demos


class CustomHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Custom help formatter with better grouping."""

    def __init__(self, prog):
        super().__init__(prog, max_help_position=30, width=80)


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser with grouped options."""
    demos = discover_demos()
    demo_list = (
        "\n".join(f"    {name:12}  {title}" for name, (title, _, _) in demos.items())
        if demos
        else "    (no demos found)"
    )

    epilog = f"""
Demos:
  Specify one or more demos to run. If none specified, runs all built-in demos.

  Built-in demos:
{demo_list}

  You can also specify:
    - External paths: ~/my-project or /path/to/demo
      (runs demo-script.py if present, otherwise runs generic demo)
    - 'all': Explicitly run all built-in demos

Examples:
  python demos/demo.py --host 46.62.169.221                  Run all demos
  python demos/demo.py --host 46.62.169.221 demo1            Run specific demo
  python demos/demo.py --host 46.62.169.221 -l demo1         Use local code
  python demos/demo.py --host 46.62.169.221 -k demo2         Keep apps running
  python demos/demo.py --host 46.62.169.221 ~/my-app         External app
  python demos/demo.py --host 46.62.169.221 -p 2 -k          Screencast mode
  python demos/demo.py --inventory                           Show detailed inventory
  python demos/demo.py --quiet --host HOST demo1             Minimal output
"""

    parser = argparse.ArgumentParser(
        prog="python demos/demo.py",
        description="Hop3 Demo Launcher - Interactive demonstrations of Hop3 deployment features.",
        epilog=textwrap.dedent(epilog),
        formatter_class=CustomHelpFormatter,
        add_help=False,
    )

    # Required arguments
    required = parser.add_argument_group("Required")
    required.add_argument(
        "-H",
        "--host",
        metavar="HOST",
        help="Target server IP address",
    )

    # Server options
    server = parser.add_argument_group("Server Options")
    server.add_argument(
        "--ssh-user",
        default="root",
        metavar="USER",
        help="SSH user for server connection (default: root)",
    )
    server.add_argument(
        "--admin-domain",
        metavar="DOMAIN",
        help="Domain for Hop3 admin UI (e.g., hop3.example.com). Required for secure HTTPS access to the dashboard.",
    )
    server.add_argument(
        "--skip-install",
        action="store_true",
        help="Skip Hop3 installation (assume already installed)",
    )
    server.add_argument(
        "--clean-before",
        action="store_true",
        help="Clean server completely before running (removes /home/hop3, database, all apps)",
    )
    server.add_argument(
        "-l",
        "--local",
        action="store_true",
        dest="use_local_code",
        help="Sync local hop3-server code via rsync",
    )
    server.add_argument(
        "--demo-dir",
        action="append",
        type=Path,
        metavar="DIR",
        dest="demo_dirs",
        help="Additional directory to search for demos (can be repeated)",
    )

    # Authentication
    auth = parser.add_argument_group("Authentication")
    auth.add_argument(
        "--admin-user",
        default="admin",
        metavar="USER",
        help="Admin username to create (default: admin)",
    )
    auth.add_argument(
        "--admin-email",
        default="admin@example.com",
        metavar="EMAIL",
        help="Admin email address (default: admin@example.com)",
    )
    auth.add_argument(
        "--admin-password",
        metavar="PWD",
        help="Admin password (auto-generated if not specified)",
    )

    # Demo execution
    execution = parser.add_argument_group("Demo Execution")
    execution.add_argument(
        "-k",
        "--keep",
        action="store_true",
        dest="no_cleanup",
        help="Keep deployed app running after demo (requires single demo)",
    )
    execution.add_argument(
        "-x",
        "--fail-fast",
        action="store_true",
        dest="fail_fast",
        help="Stop immediately on first demo failure",
    )
    execution.add_argument(
        "-p",
        "--pause",
        type=float,
        default=0.5,
        metavar="SECS",
        help="Pause between demo steps in seconds (default: 0.5)",
    )

    # Output control
    output = parser.add_argument_group("Output Control")
    output.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed output including Docker build logs",
    )
    output.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Minimal output (phases and results only)",
    )
    output.add_argument(
        "-s",
        "--silent",
        action="store_true",
        help="No output except errors (errors go to stderr)",
    )
    output.add_argument(
        "--debug",
        action="store_true",
        help="Maximum verbosity (passes --debug to hop3 for build logs)",
    )
    output.add_argument(
        "--logs-dir",
        type=Path,
        metavar="DIR",
        help="Directory for detailed logs (default: demos/logs/)",
    )
    output.add_argument(
        "--no-logs",
        action="store_true",
        help="Disable file logging entirely",
    )

    # Information
    info = parser.add_argument_group("Information")
    info.add_argument(
        "-h",
        "--help",
        action="help",
        help="Show this help message and exit",
    )
    info.add_argument(
        "--list",
        action="store_true",
        help="List available demos and exit",
    )
    info.add_argument(
        "--inventory",
        action="store_true",
        help="Show detailed inventory of all demos and exit",
    )

    # Positional arguments (demos)
    parser.add_argument(
        "demos",
        nargs="*",
        metavar="demo",
        help="Demo name(s) or path(s) to run",
    )

    return parser
