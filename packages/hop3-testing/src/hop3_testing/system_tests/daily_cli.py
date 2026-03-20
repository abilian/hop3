# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""CLI entry point for the daily system test framework."""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path

from rich.console import Console

from .config import (
    DeploymentConfig,
    HetznerConfig,
    TestConfig,
    load_config,
)
from .deployment import DeploymentManager
from .hetzner import HetznerManager
from .orchestrator import DailyTestOrchestrator
from .runner import TestRunnerManager
from .ssh import is_port_open, verify_ssh_connectivity

VERSION = "0.1.0"


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="hop3-daily-test",
        description="Hop3 Daily System Test Framework. Runs comprehensive end-to-end tests on Hetzner infrastructure.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- run command ---
    run_parser = subparsers.add_parser(
        "run",
        help="Run the daily system test",
        description="""Run the daily system test.

This command orchestrates a complete end-to-end test:
  1. Reset the Hetzner server to a clean state
  2. Deploy Hop3 from the specified branch
  3. Run all configured test suites
  4. Generate an HTML report

Environment variables:
  HETZNER_API_TOKEN  Hetzner Cloud API token (required)
  HETZNER_SERVER_ID  Server ID to use for testing
  HOP3_BRANCH        Git branch to test (default: devel)
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    run_parser.add_argument(
        "--server-id", type=int, help="Hetzner server ID to test on."
    )
    run_parser.add_argument("--branch", default="devel", help="Git branch to test.")
    run_parser.add_argument(
        "--image",
        default=None,
        help="OS image to use (e.g., ubuntu-24.04, debian-13, fedora-41, rocky-9).",
    )
    run_parser.add_argument(
        "--config", dest="config_file", type=Path, help="Path to configuration file."
    )
    run_parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("./reports"),
        help="Directory for test reports.",
    )
    run_parser.add_argument(
        "--skip-reset",
        action="store_true",
        help="Skip server reset (use existing state).",
    )
    run_parser.add_argument(
        "--skip-deploy",
        action="store_true",
        help="Skip Hop3 deployment (use existing installation).",
    )
    run_parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip test execution (only reset and deploy).",
    )
    run_parser.add_argument(
        "--suites",
        nargs="+",
        help="Test suites to run: test-apps, docker-apps, native-apps, demos, tutorials.",
    )
    run_parser.add_argument(
        "-x", "--fail-fast", action="store_true", help="Stop on first test failure."
    )
    run_parser.add_argument(
        "--random",
        dest="random_order",
        action="store_true",
        help="Run tests in random order.",
    )
    run_parser.add_argument(
        "--use-local-repo",
        action="store_true",
        help="Use local working directory instead of cloning from git.",
    )
    run_parser.add_argument(
        "--local-repo-path",
        type=Path,
        help="Path to local Hop3 repo (defaults to current directory).",
    )
    run_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output."
    )

    # --- status command ---
    status_parser = subparsers.add_parser(
        "status",
        help="Check the status of the test server",
        description="Check the status of the test server. Displays current server state and connectivity information.",
    )
    status_parser.add_argument(
        "--server-id", type=int, required=True, help="Hetzner server ID."
    )

    # --- list-images command ---
    list_images_parser = subparsers.add_parser(
        "list-images",
        help="List available OS images for testing",
        description="List available OS images that can be used with --image option.",
    )
    list_images_parser.add_argument(
        "--all",
        action="store_true",
        help="Show all Hetzner images (not just recommended ones).",
    )

    # --- reset command ---
    reset_parser = subparsers.add_parser(
        "reset",
        help="Reset the test server to a clean state",
        description="""Reset the test server to a clean state.

This will:
  1. Rebuild the server with the specified OS image
  2. Wait for SSH to become available
  3. Update SSH known_hosts with the new host key
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    reset_parser.add_argument(
        "--server-id", type=int, required=True, help="Hetzner server ID."
    )
    reset_parser.add_argument(
        "--image", default="ubuntu-24.04", help="OS image to install."
    )
    reset_parser.add_argument(
        "-y", "--yes", action="store_true", help="Skip confirmation prompt."
    )

    # --- deploy command ---
    deploy_parser = subparsers.add_parser(
        "deploy",
        help="Deploy Hop3 to the test server",
        description="Deploy Hop3 to the test server. Clones the repository and runs hop3-deploy.",
    )
    deploy_parser.add_argument(
        "--server-id", type=int, required=True, help="Hetzner server ID."
    )
    deploy_parser.add_argument(
        "--branch", default="devel", help="Git branch to deploy."
    )
    deploy_parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean existing installation before deploying.",
    )

    # --- test command ---
    test_parser = subparsers.add_parser(
        "test",
        help="Run tests against an already-deployed Hop3 server",
        description="""Run tests against an already-deployed Hop3 server.

This command runs test suites without resetting or redeploying.
Useful for re-running tests after fixing issues.

Example:
    hop3-daily-test test --server-id 12345 --suites test-apps
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    test_parser.add_argument(
        "--server-id", type=int, required=True, help="Hetzner server ID."
    )
    test_parser.add_argument(
        "--suites",
        nargs="+",
        default=["test-apps"],
        help="Test suites to run: test-apps, docker-apps, native-apps, demos, tutorials.",
    )
    test_parser.add_argument(
        "-x", "--fail-fast", action="store_true", help="Stop on first failure."
    )
    test_parser.add_argument(
        "--random",
        dest="random_order",
        action="store_true",
        help="Run tests in random order.",
    )
    test_parser.add_argument(
        "--project-root",
        type=Path,
        help="Path to Hop3 project root (for test catalog).",
    )
    test_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output."
    )

    return parser


def cmd_run(args: argparse.Namespace) -> None:
    """Execute the 'run' command."""
    console = Console()

    # Build CLI overrides
    overrides: dict = {}
    if args.server_id:
        overrides["server_id"] = args.server_id
    if args.branch != "devel":
        overrides["branch"] = args.branch
    if args.image:
        overrides["image"] = args.image
    if args.suites:
        overrides["suites"] = list(args.suites)
    if args.fail_fast:
        overrides["fail_fast"] = True
    if args.random_order:
        overrides["random_order"] = True
    if args.report_dir:
        overrides["report_dir"] = args.report_dir
    if args.use_local_repo:
        overrides["use_local_repo"] = True
    if args.local_repo_path:
        overrides["local_repo_path"] = args.local_repo_path

    # Load configuration
    try:
        config = load_config(args.config_file, overrides)
    except Exception as e:
        console.print(f"[red]Error loading configuration: {e}[/red]")
        sys.exit(1)

    # Validate configuration
    errors = config.validate()
    if errors:
        console.print("[red]Configuration errors:[/red]")
        for error in errors:
            console.print(f"  - {error}")
        sys.exit(1)

    # If skipping deploy, must also skip reset (no point resetting then not deploying)
    skip_reset = args.skip_reset
    if args.skip_deploy and not skip_reset:
        skip_reset = True

    # Run the test
    orchestrator = DailyTestOrchestrator(config, console, verbose=args.verbose)
    result = orchestrator.run(
        skip_reset=skip_reset,
        skip_deploy=args.skip_deploy,
        skip_tests=args.skip_tests,
    )

    # Exit with appropriate code
    sys.exit(0 if result.success else 1)


def cmd_list_images(args: argparse.Namespace) -> None:
    """Execute the 'list-images' command."""
    console = Console()

    # Recommended images for Hop3 testing
    # Note: Image names must match what's available on Hetzner Cloud
    recommended = [
        ("ubuntu-24.04", "Ubuntu 24.04 LTS", "Default, well-tested"),
        ("debian-13", "Debian 13 (trixie)", "Stable, supported"),
        ("debian-12", "Debian 12 (bookworm)", "Older stable"),
        ("fedora-42", "Fedora 42", "Latest Fedora"),
        ("rocky-9", "Rocky Linux 9", "RHEL-compatible"),
        ("alma-9", "AlmaLinux 9", "RHEL-compatible"),
    ]

    console.print()
    console.print("[bold]Recommended Images for Hop3 Testing[/bold]")
    console.print()
    console.print(
        "  [bold]Image Name[/bold]         [bold]Description[/bold]              [bold]Notes[/bold]"
    )
    console.print("  " + "-" * 60)
    for name, desc, notes in recommended:
        console.print(f"  {name:<18} {desc:<24} {notes}")
    console.print()
    console.print("[dim]Usage: hop3-daily-test run --image debian-13[/dim]")
    console.print()

    if args.all:
        # Try to fetch all images from Hetzner API
        api_token = os.environ.get("HETZNER_API_TOKEN")
        if api_token:
            try:
                config = HetznerConfig(
                    api_token=api_token,
                    server_id=0,  # Not needed for listing images
                    image="ubuntu-24.04",
                )
                manager = HetznerManager(config)
                images = manager.list_images()

                console.print("[bold]All Available Hetzner Images[/bold]")
                console.print()
                for img in sorted(images, key=lambda x: x.get("name", "")):
                    name = img.get("name", "unknown")
                    desc = img.get("description", "")
                    console.print(f"  {name:<25} {desc}")
            except Exception as e:
                console.print(
                    f"[yellow]Could not fetch images from Hetzner: {e}[/yellow]"
                )
        else:
            console.print(
                "[yellow]Set HETZNER_API_TOKEN to list all Hetzner images[/yellow]"
            )


def cmd_status(args: argparse.Namespace) -> None:
    """Execute the 'status' command."""
    console = Console()

    api_token = os.environ.get("HETZNER_API_TOKEN")
    if not api_token:
        console.print("[red]HETZNER_API_TOKEN environment variable not set[/red]")
        sys.exit(1)

    config = HetznerConfig(
        api_token=api_token,
        server_id=args.server_id,
        image="ubuntu-24.04",
    )

    try:
        manager = HetznerManager(config)
        info = manager.get_server_info()

        console.print()
        console.print("[bold]Server Status[/bold]")
        console.print(f"  ID:         {info.id}")
        console.print(f"  Name:       {info.name}")
        console.print(f"  Status:     {info.status.value}")
        console.print(f"  IPv4:       {info.ipv4}")
        console.print(f"  Datacenter: {info.datacenter}")
        console.print(f"  Type:       {info.server_type}")
        console.print(f"  Image:      {info.image or 'N/A'}")

        # Check SSH connectivity
        console.print()
        console.print("[bold]Connectivity[/bold]")

        if is_port_open(info.ipv4, 22):
            console.print("  SSH Port:   [green]open[/green]")
            if verify_ssh_connectivity(info.ipv4):
                console.print("  SSH Auth:   [green]ok[/green]")
            else:
                console.print("  SSH Auth:   [yellow]failed[/yellow]")
        else:
            console.print("  SSH Port:   [red]closed[/red]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


def cmd_reset(args: argparse.Namespace) -> None:
    """Execute the 'reset' command."""
    console = Console()

    api_token = os.environ.get("HETZNER_API_TOKEN")
    if not api_token:
        console.print("[red]HETZNER_API_TOKEN environment variable not set[/red]")
        sys.exit(1)

    # Confirmation prompt
    if not args.yes:
        response = input("This will wipe all data on the server. Continue? [y/N] ")
        if response.lower() not in {"y", "yes"}:
            console.print("Aborted.")
            sys.exit(0)

    config = HetznerConfig(
        api_token=api_token,
        server_id=args.server_id,
        image=args.image,
    )

    manager = HetznerManager(config)
    console.print(f"Rebuilding server {args.server_id} with image '{args.image}'...")

    try:
        info = manager.rebuild_server(image=args.image)
        console.print("[green]Server rebuilt successfully[/green]")
        console.print("Waiting for SSH...")
        if manager.wait_for_ssh_ready():
            console.print("[green]SSH is ready[/green]")
            console.print(f"  Connect with: ssh root@{info.ipv4}")
        else:
            console.print("[yellow]SSH not ready within timeout[/yellow]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


def cmd_deploy(args: argparse.Namespace) -> None:
    """Execute the 'deploy' command."""
    console = Console()

    api_token = os.environ.get("HETZNER_API_TOKEN")
    if not api_token:
        console.print("[red]HETZNER_API_TOKEN environment variable not set[/red]")
        sys.exit(1)

    hetzner_config = HetznerConfig(
        api_token=api_token,
        server_id=args.server_id,
        image="ubuntu-24.04",
    )

    try:
        # Get server IP
        manager = HetznerManager(hetzner_config)
        info = manager.get_server_info()
        server_ip = info.ipv4

        console.print(f"Deploying to {info.name} ({server_ip})")

        deploy_config = DeploymentConfig(
            branch=args.branch,
            use_local_code=True,
            clean_before=args.clean,
            verbose=True,
        )

        deployer = DeploymentManager(
            host=server_ip,
            config=deploy_config,
        )

        try:
            console.print(f"Cloning branch '{args.branch}'...")
            deployer.clone_repo()

            console.print("Running deployment...")
            result = deployer.deploy()

            if result.success:
                console.print("[green]Deployment successful![/green]")
                console.print(f"  Server URL: {result.server_url}")
                console.print(f"  Duration: {result.duration:.1f}s")
            else:
                console.print(f"[red]Deployment failed: {result.error}[/red]")
                sys.exit(1)

        finally:
            deployer.cleanup()

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


def cmd_test(args: argparse.Namespace) -> None:
    """Execute the 'test' command."""
    console = Console()

    api_token = os.environ.get("HETZNER_API_TOKEN")
    if not api_token:
        console.print("[red]HETZNER_API_TOKEN environment variable not set[/red]")
        sys.exit(1)

    hetzner_config = HetznerConfig(
        api_token=api_token,
        server_id=args.server_id,
        image="ubuntu-24.04",
    )

    try:
        # Get server IP
        manager = HetznerManager(hetzner_config)
        info = manager.get_server_info()
        server_ip = info.ipv4

        console.print(f"Running tests on {info.name} ({server_ip})")

        # Create test config
        test_config = TestConfig(
            suites=list(args.suites),
            fail_fast=args.fail_fast,
            random_order=args.random_order,
        )

        # Run tests
        runner = TestRunnerManager(
            host=server_ip,
            config=test_config,
            project_root=args.project_root,
            console=console,
            verbose=args.verbose,
        )

        result = runner.run_all_suites()

        # Print summary
        console.print()
        console.print("[bold]Test Results:[/bold]")
        for suite_result in result.suite_results:
            icon = "[green]✓[/green]" if suite_result.success else "[red]✗[/red]"
            console.print(f"  {icon} {suite_result.summary}")

        console.print()
        console.print(
            f"Total: {result.total_tests} tests, "
            f"{result.total_passed} passed, "
            f"{result.total_failed} failed"
        )

        sys.exit(0 if result.success else 1)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if args.verbose:
            traceback.print_exc()
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    # Dispatch to command handler
    commands = {
        "run": cmd_run,
        "list-images": cmd_list_images,
        "status": cmd_status,
        "reset": cmd_reset,
        "deploy": cmd_deploy,
        "test": cmd_test,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
