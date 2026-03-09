# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""CLI entry point for the daily system test framework."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

from .config import Config, load_config
from .orchestrator import DailyTestOrchestrator


@click.group()
@click.version_option(version="0.1.0", prog_name="hop3-daily-test")
def cli() -> None:
    """Hop3 Daily System Test Framework.

    Runs comprehensive end-to-end tests on Hetzner infrastructure.
    """


@cli.command()
@click.option(
    "--server-id",
    type=int,
    envvar="HETZNER_SERVER_ID",
    help="Hetzner server ID to test on.",
)
@click.option(
    "--branch",
    default="devel",
    envvar="HOP3_BRANCH",
    help="Git branch to test.",
)
@click.option(
    "--config",
    "config_file",
    type=click.Path(exists=True, path_type=Path),
    help="Path to configuration file.",
)
@click.option(
    "--report-dir",
    type=click.Path(path_type=Path),
    default="./reports",
    help="Directory for test reports.",
)
@click.option(
    "--skip-reset",
    is_flag=True,
    help="Skip server reset (use existing state).",
)
@click.option(
    "--skip-deploy",
    is_flag=True,
    help="Skip Hop3 deployment (use existing installation).",
)
@click.option(
    "--skip-tests",
    is_flag=True,
    help="Skip test execution (only reset and deploy).",
)
@click.option(
    "--suites",
    multiple=True,
    help="Test suites to run (can be specified multiple times).",
)
@click.option(
    "--use-local-repo",
    is_flag=True,
    help="Use local working directory instead of cloning from git.",
)
@click.option(
    "--local-repo-path",
    type=click.Path(exists=True, path_type=Path),
    help="Path to local Hop3 repo (defaults to current directory).",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Enable verbose output.",
)
def run(
    server_id: int | None,
    branch: str,
    config_file: Path | None,
    report_dir: Path,
    skip_reset: bool,
    skip_deploy: bool,
    skip_tests: bool,
    suites: tuple[str, ...],
    use_local_repo: bool,
    local_repo_path: Path | None,
    verbose: bool,
) -> None:
    """Run the daily system test.

    This command orchestrates a complete end-to-end test:

    1. Reset the Hetzner server to a clean state
    2. Deploy Hop3 from the specified branch
    3. Run all configured test suites
    4. Generate an HTML report

    Environment variables:
      HETZNER_API_TOKEN  Hetzner Cloud API token (required)
      HETZNER_SERVER_ID  Server ID to use for testing
      HOP3_BRANCH        Git branch to test (default: devel)
    """
    console = Console()

    # Build CLI overrides
    overrides = {}
    if server_id:
        overrides["server_id"] = server_id
    if branch != "devel":
        overrides["branch"] = branch
    if suites:
        overrides["suites"] = list(suites)
    if report_dir:
        overrides["report_dir"] = report_dir
    if use_local_repo:
        overrides["use_local_repo"] = True
    if local_repo_path:
        overrides["local_repo_path"] = local_repo_path

    # Load configuration
    try:
        config = load_config(config_file, overrides)
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

    # Run the test
    orchestrator = DailyTestOrchestrator(config, console)
    result = orchestrator.run(
        skip_reset=skip_reset,
        skip_deploy=skip_deploy,
        skip_tests=skip_tests,
    )

    # Exit with appropriate code
    sys.exit(0 if result.success else 1)


@cli.command()
@click.option(
    "--server-id",
    type=int,
    envvar="HETZNER_SERVER_ID",
    required=True,
    help="Hetzner server ID.",
)
def status(server_id: int) -> None:
    """Check the status of the test server.

    Displays current server state and connectivity information.
    """
    from .hetzner import HetznerManager
    from .config import HetznerConfig
    import os

    console = Console()

    api_token = os.environ.get("HETZNER_API_TOKEN")
    if not api_token:
        console.print("[red]HETZNER_API_TOKEN environment variable not set[/red]")
        sys.exit(1)

    config = HetznerConfig(
        api_token=api_token,
        server_id=server_id,
    )

    try:
        manager = HetznerManager(config)
        info = manager.get_server_info()

        console.print()
        console.print(f"[bold]Server Status[/bold]")
        console.print(f"  ID:         {info.id}")
        console.print(f"  Name:       {info.name}")
        console.print(f"  Status:     {info.status.value}")
        console.print(f"  IPv4:       {info.ipv4}")
        console.print(f"  Datacenter: {info.datacenter}")
        console.print(f"  Type:       {info.server_type}")
        console.print(f"  Image:      {info.image or 'N/A'}")

        # Check SSH connectivity
        from .ssh import is_port_open, verify_ssh_connectivity

        console.print()
        console.print("[bold]Connectivity[/bold]")

        if is_port_open(info.ipv4, 22):
            console.print(f"  SSH Port:   [green]open[/green]")
            if verify_ssh_connectivity(info.ipv4):
                console.print(f"  SSH Auth:   [green]ok[/green]")
            else:
                console.print(f"  SSH Auth:   [yellow]failed[/yellow]")
        else:
            console.print(f"  SSH Port:   [red]closed[/red]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option(
    "--server-id",
    type=int,
    envvar="HETZNER_SERVER_ID",
    required=True,
    help="Hetzner server ID.",
)
@click.option(
    "--image",
    default="debian-12",
    help="OS image to install.",
)
@click.confirmation_option(
    prompt="This will wipe all data on the server. Continue?",
)
def reset(server_id: int, image: str) -> None:
    """Reset the test server to a clean state.

    This will:
    1. Rebuild the server with the specified OS image
    2. Wait for SSH to become available
    3. Update SSH known_hosts with the new host key
    """
    from .hetzner import HetznerManager
    from .config import HetznerConfig
    import os

    console = Console()

    api_token = os.environ.get("HETZNER_API_TOKEN")
    if not api_token:
        console.print("[red]HETZNER_API_TOKEN environment variable not set[/red]")
        sys.exit(1)

    config = HetznerConfig(
        api_token=api_token,
        server_id=server_id,
        image=image,
    )

    try:
        manager = HetznerManager(config)

        console.print(f"Rebuilding server {server_id} with image '{image}'...")

        info = manager.rebuild_server(image=image)
        console.print(f"[green]Server rebuilt successfully[/green]")

        console.print("Waiting for SSH...")
        if manager.wait_for_ssh_ready():
            console.print(f"[green]SSH is ready[/green]")
            console.print(f"  Connect with: ssh root@{info.ipv4}")
        else:
            console.print(f"[yellow]SSH not ready within timeout[/yellow]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option(
    "--server-id",
    type=int,
    envvar="HETZNER_SERVER_ID",
    required=True,
    help="Hetzner server ID.",
)
@click.option(
    "--branch",
    default="devel",
    envvar="HOP3_BRANCH",
    help="Git branch to deploy.",
)
@click.option(
    "--clean",
    is_flag=True,
    help="Clean existing installation before deploying.",
)
def deploy(server_id: int, branch: str, clean: bool) -> None:
    """Deploy Hop3 to the test server.

    Clones the repository and runs hop3-deploy.
    """
    from .hetzner import HetznerManager
    from .deployment import DeploymentManager
    from .config import HetznerConfig, DeploymentConfig
    import os

    console = Console()

    api_token = os.environ.get("HETZNER_API_TOKEN")
    if not api_token:
        console.print("[red]HETZNER_API_TOKEN environment variable not set[/red]")
        sys.exit(1)

    hetzner_config = HetznerConfig(
        api_token=api_token,
        server_id=server_id,
    )

    try:
        # Get server IP
        manager = HetznerManager(hetzner_config)
        info = manager.get_server_info()
        server_ip = info.ipv4

        console.print(f"Deploying to {info.name} ({server_ip})")

        deploy_config = DeploymentConfig(
            branch=branch,
            use_local_code=True,
            clean_before=clean,
            verbose=True,
        )

        deployer = DeploymentManager(
            host=server_ip,
            config=deploy_config,
        )

        try:
            console.print(f"Cloning branch '{branch}'...")
            deployer.clone_repo()

            console.print("Running deployment...")
            result = deployer.deploy()

            if result.success:
                console.print(f"[green]Deployment successful![/green]")
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


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
