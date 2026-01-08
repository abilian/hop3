# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Hop3 unified installer CLI.

Provides a single entry point for all installer operations:
- hop3-install cli      - Install Hop3 CLI locally
- hop3-install server   - Install Hop3 server on remote machine
- hop3-install bundle   - Bundle installers into single files
- hop3-install test     - Test installers in Docker/SSH/Vagrant

Usage:
    hop3-install cli [options]
    hop3-install server [options]
    hop3-install bundle [options]
    hop3-install test [options]
    hop3-install --help
"""

from __future__ import annotations

import sys


def main() -> int:
    """Main entry point for hop3-install."""
    if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help"}:
        print_help()
        return 0

    subcommand = sys.argv[1]

    # Remove the subcommand from argv so the submodule sees its own args
    sys.argv = [f"hop3-install {subcommand}"] + sys.argv[2:]

    match subcommand:
        case "cli":
            from .cli_installer.installer import main as cli_main

            return cli_main()
        case "server":
            from .server_installer.installer import main as server_main

            return server_main()
        case "bundle":
            from .bundler import main as bundler_main

            return bundler_main()
        case "test":
            from .testing import main as testing_main

            return testing_main()
        case _:
            print(f"Unknown subcommand: {subcommand}")
            print_help()
            return 1


def print_help() -> None:
    """Print help message."""
    print("""hop3-install - Hop3 installer toolkit

Usage:
    hop3-install <command> [options]

Commands:
    cli       Install Hop3 CLI tool locally
    server    Install Hop3 server (run as root on target server)
    bundle    Bundle installers into single-file scripts
    test      Test installers (Docker, SSH, or Vagrant backends)

Examples:
    # Install CLI locally (from PyPI)
    hop3-install cli

    # Install CLI from git
    hop3-install cli --git

    # Install server (must be run as root)
    sudo hop3-install server

    # Bundle all installers
    hop3-install bundle --all --output-dir dist/

    # Test installers in Docker
    hop3-install test docker --distro ubuntu

Run 'hop3-install <command> --help' for more information on a command.
""")


if __name__ == "__main__":
    sys.exit(main())
