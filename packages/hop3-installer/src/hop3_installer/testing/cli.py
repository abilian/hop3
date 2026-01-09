# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""CLI for Hop3 installer testing.

Supports multiple backends: SSH (remote servers), Docker (containers),
and Vagrant (virtual machines).

Usage:
    # SSH backend (remote server)
    hop3-install test ssh --host root@server.example.com
    hop3-install test ssh --host user@server --method git --type both

    # Docker backend (containers)
    hop3-install test docker --distro ubuntu
    hop3-install test docker --distro fedora --type cli

    # Vagrant backend (VMs)
    hop3-install test vagrant --vm ubuntu
    hop3-install test vagrant --vm fedora --type server

Common options:
    --type TYPE         Installer to test: cli, server, or both (default: both)
    --method METHOD     Installation method: pypi, git, local, or all (default: git)
    --branch BRANCH     Git branch for git method (default: devel)
    --version VERSION   Version for pypi method
    --keep              Keep environment after test
    --verbose           Show verbose output
    --dry-run           Show commands without executing (SSH only)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from hop3_installer.common import find_project_root

from .common import log_error, log_header, set_dry_run, set_verbose
from .runner import INSTALL_METHODS, TestConfig, TestRunner

# Available distros/VMs for each backend
DOCKER_DISTROS = ["ubuntu", "debian", "fedora"]
VAGRANT_VMS = ["ubuntu", "debian", "fedora"]


def _find_or_generate_installer_dir() -> Path:
    """Find or generate the single-file installers.

    Looks for installer/ in the project root. If installers don't exist,
    generates them using the bundler.
    """
    project_root = find_project_root(Path(__file__).parent)

    # Check for existing installers in installer/ directory
    installer_dir = project_root / "installer"
    if (
        installer_dir.exists()
        and (installer_dir / "install-server.py").exists()
        and (installer_dir / "install-cli.py").exists()
    ):
        return installer_dir

    # Generate installers if they don't exist
    print("[INFO] Generating single-file installers...")
    installer_dir.mkdir(exist_ok=True)

    from hop3_installer.bundler import bundle_installer

    try:
        # Generate CLI installer
        cli_path = installer_dir / "install-cli.py"
        cli_content = bundle_installer("cli")
        cli_path.write_text(cli_content)
        cli_path.chmod(0o755)
        print(f"  Generated: {cli_path}")

        # Generate server installer
        server_path = installer_dir / "install-server.py"
        server_content = bundle_installer("server")
        server_path.write_text(server_content)
        server_path.chmod(0o755)
        print(f"  Generated: {server_path}")

        return installer_dir
    except Exception as e:
        log_error(f"Failed to generate installers: {e}")
        raise


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="hop3-install test",
        description="Unified test script for Hop3 installers.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Create subparsers for each backend
    subparsers = parser.add_subparsers(dest="backend", help="Test backend to use")

    # SSH backend
    ssh_parser = subparsers.add_parser(
        "ssh",
        help="Test on remote server via SSH",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    hop3-install test ssh --host root@server.example.com
    hop3-install test ssh --host user@server --type both --method git
    hop3-install test ssh --host user@server --method pypi --version 0.4.0
        """,
    )
    ssh_parser.add_argument(
        "--host",
        metavar="HOST",
        default=os.environ.get("HOP3_TEST_HOST"),
        help="SSH target (hostname or user@hostname). Can also set HOP3_TEST_HOST env var",
    )
    ssh_parser.add_argument(
        "--user",
        "-u",
        metavar="USER",
        default=os.environ.get("HOP3_SSH_USER", "root"),
        help="SSH user (default: root, or set HOP3_SSH_USER env var)",
    )
    ssh_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show commands without executing",
    )
    _add_common_args(ssh_parser)

    # Docker backend
    docker_parser = subparsers.add_parser(
        "docker",
        help="Test in Docker containers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    hop3-install test docker --distro ubuntu
    hop3-install test docker --distro fedora --type cli
    hop3-install test docker --all

Note: Server tests are limited in Docker (no systemd).
        """,
    )
    docker_parser.add_argument(
        "--distro",
        choices=DOCKER_DISTROS,
        default="ubuntu",
        help="Distribution to test on (default: ubuntu)",
    )
    docker_parser.add_argument(
        "--all",
        action="store_true",
        help="Test on all available distros",
    )
    docker_parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove all test containers and exit",
    )
    _add_common_args(docker_parser)

    # Vagrant backend
    vagrant_parser = subparsers.add_parser(
        "vagrant",
        help="Test in Vagrant VMs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    hop3-install test vagrant --vm ubuntu
    hop3-install test vagrant --vm fedora --type server
    hop3-install test vagrant --all

Requires: Vagrant and VirtualBox (or another provider).
        """,
    )
    vagrant_parser.add_argument(
        "--vm",
        choices=VAGRANT_VMS,
        default="ubuntu",
        help="VM to test on (default: ubuntu)",
    )
    vagrant_parser.add_argument(
        "--all",
        action="store_true",
        help="Test on all available VMs",
    )
    vagrant_parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Destroy all VMs and exit",
    )
    _add_common_args(vagrant_parser)

    return parser


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add common arguments to a subparser."""
    parser.add_argument(
        "--type",
        choices=["cli", "server", "both"],
        default="both",
        help="Installer type to test (default: both)",
    )
    parser.add_argument(
        "--method",
        choices=INSTALL_METHODS + ["all"],
        default="git",
        help="Installation method to test (default: git)",
    )
    parser.add_argument(
        "--branch",
        metavar="BRANCH",
        default=os.environ.get("HOP3_BRANCH", "devel"),
        help="Git branch for git method (default: devel)",
    )
    parser.add_argument(
        "--version",
        metavar="VERSION",
        default=os.environ.get("HOP3_VERSION"),
        help="Specific version for pypi method",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep environment after test",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )


def run_ssh_tests(args: argparse.Namespace, installer_dir: Path) -> int:
    """Run tests using SSH backend."""
    from .backends.ssh import SSHBackend

    if not args.host:
        log_error(
            "No host specified. Use --host or set HOP3_TEST_HOST environment variable"
        )
        print()
        print("Example:")
        print("  hop3-install test ssh --host server.example.com")
        print("  hop3-install test ssh --host root@server.example.com")
        return 1

    # Build SSH target (user@host format)
    if "@" in args.host:
        ssh_target = args.host
    else:
        ssh_target = f"{args.user}@{args.host}"

    # Print test plan
    log_header("Hop3 Installer E2E Tests (SSH)")
    print(f"  Host:    {ssh_target}")
    print(f"  Type:    {args.type}")
    print(f"  Method:  {args.method}")
    print(f"  Branch:  {args.branch}")
    if args.version:
        print(f"  Version: {args.version}")
    print()

    # Create backend and config
    backend = SSHBackend(ssh_target)
    config = TestConfig(
        method=args.method if args.method != "all" else "git",
        branch=args.branch,
        version=args.version,
        installer_dir=installer_dir,
        skip_acme=True,
    )

    # Setup
    if not backend.setup():
        return 1

    # Determine methods to test
    methods = INSTALL_METHODS if args.method == "all" else [args.method]

    # Run tests
    runner = TestRunner(backend, config)
    try:
        if args.type in {"cli", "both"}:
            log_header("CLI Installer Tests")
            runner.run_cli_tests(methods)

        if args.type in {"server", "both"}:
            log_header("Server Installer Tests")
            runner.run_server_tests(methods)
    finally:
        if not args.keep:
            if args.type in {"cli", "both"}:
                backend.cleanup_cli()
            if args.type in {"server", "both"}:
                backend.cleanup_server()

    # Summary
    return 0 if runner.print_summary() else 1


def run_docker_tests(args: argparse.Namespace, installer_dir: Path) -> int:
    """Run tests using Docker backend."""
    from .backends.docker import DockerBackend

    # Handle cleanup
    if args.cleanup:
        log_header("Cleaning up Docker containers")
        for distro in DOCKER_DISTROS:
            backend = DockerBackend(distro, installer_dir)
            backend.teardown()
        print("Cleanup complete")
        return 0

    # Determine distros to test
    distros = DOCKER_DISTROS if args.all else [args.distro]

    # Print test plan
    log_header("Hop3 Installer Tests (Docker)")
    print(f"  Distros: {', '.join(distros)}")
    print(f"  Type:    {args.type}")
    print(f"  Method:  {args.method}")
    print()

    all_results = {}

    for distro in distros:
        log_header(f"Testing on {distro}")

        backend = DockerBackend(distro, installer_dir)
        config = TestConfig(
            method=args.method if args.method != "all" else "git",
            branch=args.branch,
            installer_dir=installer_dir,
        )

        if not backend.setup():
            all_results[distro] = False
            continue

        runner = TestRunner(backend, config)
        try:
            methods = INSTALL_METHODS if args.method == "all" else [args.method]

            if args.type in {"cli", "both"}:
                runner.run_cli_tests(methods)

            if args.type in {"server", "both"}:
                runner.run_server_tests(methods)

            all_results[distro] = all(r.passed for r in runner.results)
        finally:
            if not args.keep:
                backend.teardown()

    # Overall summary
    log_header("Overall Summary")
    total = len(all_results)
    passed = sum(1 for v in all_results.values() if v)
    print(f"  Total:  {total}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {total - passed}")

    return 0 if passed == total else 1


def run_vagrant_tests(args: argparse.Namespace, installer_dir: Path) -> int:
    """Run tests using Vagrant backend."""
    from .backends.vagrant import VagrantBackend

    # Handle cleanup
    if args.cleanup:
        log_header("Cleaning up Vagrant VMs")
        for vm in VAGRANT_VMS:
            backend = VagrantBackend(vm, installer_dir)
            backend.teardown()
        print("Cleanup complete")
        return 0

    # Determine VMs to test
    vms = VAGRANT_VMS if args.all else [args.vm]

    # Print test plan
    log_header("Hop3 Installer Tests (Vagrant)")
    print(f"  VMs:     {', '.join(vms)}")
    print(f"  Type:    {args.type}")
    print(f"  Method:  {args.method}")
    print()

    all_results = {}

    for vm in vms:
        log_header(f"Testing on {vm}")

        backend = VagrantBackend(vm, installer_dir)
        config = TestConfig(
            method=args.method if args.method != "all" else "git",
            branch=args.branch,
            installer_dir=installer_dir,
        )

        if not backend.setup():
            all_results[vm] = False
            continue

        runner = TestRunner(backend, config)
        try:
            methods = INSTALL_METHODS if args.method == "all" else [args.method]

            if args.type in {"cli", "both"}:
                runner.run_cli_tests(methods)

            if args.type in {"server", "both"}:
                runner.run_server_tests(methods)

            all_results[vm] = all(r.passed for r in runner.results)
        finally:
            if not args.keep:
                backend.teardown()
            else:
                backend.stop()

    # Overall summary
    log_header("Overall Summary")
    total = len(all_results)
    passed = sum(1 for v in all_results.values() if v)
    print(f"  Total:  {total}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {total - passed}")

    return 0 if passed == total else 1


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Check backend was specified
    if not args.backend:
        parser.print_help()
        print()
        print("Please specify a backend: ssh, docker, or vagrant")
        return 1

    # Set global flags
    set_verbose(value=args.verbose)
    if hasattr(args, "dry_run") and args.dry_run:
        set_dry_run(value=True)

    # Find or generate installer directory
    installer_dir = _find_or_generate_installer_dir()

    # Run appropriate backend
    match args.backend:
        case "ssh":
            return run_ssh_tests(args, installer_dir)
        case "docker":
            return run_docker_tests(args, installer_dir)
        case "vagrant":
            return run_vagrant_tests(args, installer_dir)
        case _:
            log_error(f"Unknown backend: {args.backend}")
            return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nTests cancelled.")
        sys.exit(130)
    except Exception as e:
        log_error(f"Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
