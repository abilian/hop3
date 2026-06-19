# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Command-line interface for the demo launcher.

Two subcommands:

    python demos/demo.py run  [options] [demos...]   # run one or more demos
    python demos/demo.py list [-v] [--select/--skip] # list (and filter) demos

For convenience, a bare invocation (`demos/demo.py --backend docker demo01`)
is treated as `run ...` — see demo.py's argv shim.
"""

from __future__ import annotations

import argparse
import textwrap
from pathlib import Path


class CustomHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Custom help formatter with better grouping."""

    def __init__(self, prog):
        super().__init__(prog, max_help_position=30, width=80)


def _add_selection_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the feature-tag --select / --skip filters (shared by run + list)."""
    group = parser.add_argument_group("Feature selection")
    group.add_argument(
        "--select",
        action="append",
        default=[],
        metavar="TAG",
        help=(
            "Only demos whose tags match TAG. Repeatable (AND); comma-separated "
            "value is OR. A bare namespace matches any value. "
            "E.g. --select toolchain:python --select addon:postgres"
        ),
    )
    group.add_argument(
        "--skip",
        action="append",
        default=[],
        metavar="TAG",
        help=(
            "Exclude demos whose tags match TAG (OR; comma-separated / repeatable). "
            "E.g. --skip extra:backup --skip builder:docker"
        ),
    )


def _add_run_arguments(parser: argparse.ArgumentParser) -> None:
    """Populate the `run` subcommand's options."""
    target = parser.add_argument_group("Target")
    target.add_argument(
        "-H", "--host", metavar="HOST", help="Target server IP (required for ssh)"
    )
    target.add_argument(
        "-b",
        "--backend",
        choices=["ssh", "docker"],
        default="ssh",
        help="ssh (remote server) or docker (local container). Default: ssh",
    )
    target.add_argument(
        "--ssh-user", default="root", metavar="USER", help="SSH user (default: root)"
    )
    target.add_argument(
        "--docker-image",
        default="ubuntu:24.04",
        metavar="IMAGE",
        help="Docker image for the container backend (default: ubuntu:24.04)",
    )
    target.add_argument(
        "--docker-container",
        default="hop3-demo",
        metavar="NAME",
        help="Docker container name (default: hop3-demo)",
    )
    target.add_argument(
        "--admin-domain",
        metavar="DOMAIN",
        help="Domain for the Hop3 admin UI (e.g. hop3.example.com)",
    )
    target.add_argument(
        "--skip-install",
        action="store_true",
        help="Skip Hop3 installation (assume already installed)",
    )
    target.add_argument(
        "--clean-before",
        action="store_true",
        help="Clean the server completely before running (removes apps + database)",
    )
    target.add_argument(
        "-l",
        "--local",
        action="store_true",
        dest="use_local_code",
        help="Sync local hop3-server code via rsync",
    )
    target.add_argument(
        "--demo-dir",
        action="append",
        type=Path,
        metavar="DIR",
        dest="demo_dirs",
        help="Additional directory to search for demos (repeatable)",
    )

    auth = parser.add_argument_group("Authentication")
    auth.add_argument(
        "--admin-user", default="admin", metavar="USER", help="Admin user (default: admin)"
    )
    auth.add_argument(
        "--admin-email",
        default="admin@example.com",
        metavar="EMAIL",
        help="Admin email (default: admin@example.com)",
    )
    auth.add_argument(
        "--admin-password", metavar="PWD", help="Admin password (auto-generated if unset)"
    )

    _add_selection_arguments(parser)

    execution = parser.add_argument_group("Execution")
    execution.add_argument(
        "-Q",
        "--quick",
        action="store_true",
        help="Only re-run demos that failed previously (plus any new ones)",
    )
    execution.add_argument(
        "--clear-results",
        action="store_true",
        help="Clear stored results for this host before running",
    )
    execution.add_argument(
        "-k",
        "--keep",
        action="store_true",
        dest="no_cleanup",
        help="Keep the deployed app running afterwards (single demo only)",
    )
    execution.add_argument(
        "-x", "--fail-fast", action="store_true", dest="fail_fast",
        help="Stop on the first demo failure",
    )
    execution.add_argument(
        "-p", "--pause", type=float, default=0.5, metavar="SECS",
        help="Pause between demo steps (default: 0.5)",
    )
    execution.add_argument(
        "--preflight",
        action="store_true",
        help="Run preflight checks (SSH, DNS, OS version). Skipped by default.",
    )

    output = parser.add_argument_group("Output")
    output.add_argument(
        "-v", "--verbose", action="store_true", help="Detailed output (build logs)"
    )
    output.add_argument(
        "-q", "--quiet", action="store_true", help="Minimal output (phases + results)"
    )
    output.add_argument(
        "-s", "--silent", action="store_true", help="No output except errors (stderr)"
    )
    output.add_argument(
        "--debug", action="store_true", help="Maximum verbosity (passes --debug to hop3)"
    )
    output.add_argument(
        "--logs-dir", type=Path, metavar="DIR", help="Log directory (default: demos/logs/)"
    )
    output.add_argument(
        "--no-logs", action="store_true", help="Disable file logging entirely"
    )

    parser.add_argument(
        "demos", nargs="*", metavar="demo", help="Demo name(s) or path(s) (default: all)"
    )


def create_parser() -> argparse.ArgumentParser:
    """Create the top-level parser with `run` and `list` subcommands."""
    run_epilog = textwrap.dedent("""
        Pass demo names, external app paths, or 'all' (default: all).
        See what's available with:  python demos/demo.py list

        Examples:
          python demos/demo.py run --backend docker                 All demos, local Docker
          python demos/demo.py run --host 1.2.3.4 demo01            One demo over SSH
          python demos/demo.py run --backend docker -l demo01       Test local hop3-server code
          python demos/demo.py run --backend docker -k demo01       Keep the app running
          python demos/demo.py run --select toolchain:python        Only Python demos
          python demos/demo.py run --select addon:postgres --skip builder:docker
    """)

    parser = argparse.ArgumentParser(
        prog="python demos/demo.py",
        description="Hop3 Demo Launcher — run and inspect Hop3 capability demos.",
        formatter_class=CustomHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", metavar="{run,list}")

    run_p = sub.add_parser(
        "run",
        help="Run one or more demos",
        description="Deploy and exercise demos on a target server.",
        epilog=run_epilog,
        formatter_class=CustomHelpFormatter,
    )
    _add_run_arguments(run_p)

    list_p = sub.add_parser(
        "list",
        help="List available demos (-v for details + tags)",
        description="List discoverable demos, optionally filtered by feature tags.",
        formatter_class=CustomHelpFormatter,
    )
    list_p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show details + capability tags (the old --inventory)",
    )
    list_p.add_argument(
        "--demo-dir",
        action="append",
        type=Path,
        metavar="DIR",
        dest="demo_dirs",
        help="Additional directory to search for demos (repeatable)",
    )
    _add_selection_arguments(list_p)

    return parser
