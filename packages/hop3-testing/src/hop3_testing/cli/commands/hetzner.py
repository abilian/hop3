# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for Hetzner-based system testing.

These commands run full E2E tests on Hetzner Cloud infrastructure.
"""

from __future__ import annotations

import sys

import click


def _build_daily_argv(
    server_id: int | None,
    branch: str,
    image: str | None,
    config_file: str | None,
    report_dir: str,
    skip_reset: bool,
    skip_deploy: bool,
    skip_tests: bool,
    suites: tuple[str, ...],
    fail_fast: bool,
    random_order: bool,
    use_local_repo: bool,
    local_repo_path: str | None,
    verbose: bool,
) -> list[str]:
    """Build argv list for daily CLI."""
    argv = ["daily-test", "run"]

    # Value options
    options = [
        (server_id, "--server-id", str(server_id) if server_id else None),
        (branch != "devel", "--branch", branch),
        (image, "--image", image),
        (config_file, "--config", config_file),
        (report_dir != "./reports", "--report-dir", report_dir),
        (local_repo_path, "--local-repo-path", local_repo_path),
    ]
    for condition, flag, value in options:
        if condition and value:
            argv.extend([flag, value])

    # Flag options
    flags = [
        (skip_reset, "--skip-reset"),
        (skip_deploy, "--skip-deploy"),
        (skip_tests, "--skip-tests"),
        (fail_fast, "--fail-fast"),
        (random_order, "--random"),
        (use_local_repo, "--use-local-repo"),
        (verbose, "--verbose"),
    ]
    for condition, flag in flags:
        if condition:
            argv.append(flag)

    # Suites
    for suite in suites:
        argv.extend(["--suites", suite])

    return argv


@click.command("hetzner")
@click.option("--server-id", type=int, help="Hetzner server ID to test on.")
@click.option("--branch", default="devel", help="Git branch to test.")
@click.option(
    "--image",
    default=None,
    help="OS image (e.g., ubuntu-24.04, debian-13, fedora-42).",
)
@click.option("--config", "config_file", type=click.Path(), help="Config file path.")
@click.option(
    "--report-dir",
    type=click.Path(),
    default="./reports",
    help="Directory for test reports.",
)
@click.option("--skip-reset", is_flag=True, help="Skip server reset.")
@click.option("--skip-deploy", is_flag=True, help="Skip Hop3 deployment.")
@click.option("--skip-tests", is_flag=True, help="Skip test execution.")
@click.option("--suites", multiple=True, help="Test suites to run.")
@click.option("-x", "--fail-fast", is_flag=True, help="Stop on first failure.")
@click.option("--random", "random_order", is_flag=True, help="Random test order.")
@click.option("--use-local-repo", is_flag=True, help="Use local repository.")
@click.option("--local-repo-path", type=click.Path(), help="Path to local Hop3 repo.")
@click.option("-v", "--verbose", is_flag=True, help="Verbose output.")
@click.pass_context
def hetzner_test(
    ctx: click.Context,
    server_id: int | None,
    branch: str,
    image: str | None,
    config_file: str | None,
    report_dir: str,
    skip_reset: bool,
    skip_deploy: bool,
    skip_tests: bool,
    suites: tuple[str, ...],
    fail_fast: bool,
    random_order: bool,
    use_local_repo: bool,
    local_repo_path: str | None,
    verbose: bool,
) -> None:
    """Run system test on Hetzner Cloud infrastructure.

    This command orchestrates a complete end-to-end test:

    \b
      1. Reset the Hetzner server to a clean state
      2. Deploy Hop3 from the specified branch
      3. Run all configured test suites
      4. Generate an HTML report

    Requires HETZNER_API_TOKEN environment variable.
    """
    argv = _build_daily_argv(
        server_id,
        branch,
        image,
        config_file,
        report_dir,
        skip_reset,
        skip_deploy,
        skip_tests,
        suites,
        fail_fast,
        random_order,
        use_local_repo,
        local_repo_path,
        verbose,
    )

    # Import and run the daily CLI
    from hop3_testing.system_tests.daily_cli import main  # noqa: PLC0415

    old_argv = sys.argv
    try:
        sys.argv = argv
        main()
    finally:
        sys.argv = old_argv


@click.command("multi-distro")
@click.option("--images", multiple=True, help="Images to test (default: all).")
@click.option("--suites", default="test-apps", help="Test suites to run.")
@click.option("--use-local-repo/--no-local-repo", default=True, help="Use local repo.")
@click.option("--continue-on-failure", is_flag=True, help="Continue after failure.")
@click.option("--list-images", is_flag=True, help="List recommended images.")
@click.option("-v", "--verbose", is_flag=True, help="Verbose output.")
@click.pass_context
def multi_distro_test(
    ctx: click.Context,
    images: tuple[str, ...],
    suites: str,
    use_local_repo: bool,
    continue_on_failure: bool,
    list_images: bool,
    verbose: bool,
) -> None:
    """Run tests across multiple Linux distributions.

    Tests Hop3 on multiple OS images (Ubuntu, Debian, Fedora, etc.)
    and reports results for each distribution.

    Requires HETZNER_API_TOKEN environment variable.
    """
    # Lazy imports to avoid loading when not needed
    from rich.console import Console  # noqa: PLC0415
    from rich.table import Table  # noqa: PLC0415

    from hop3_testing.system_tests.multi_distro import (  # noqa: PLC0415
        RECOMMENDED_IMAGES,
        run_multi_distro_tests,
    )

    console = Console()

    if list_images:
        console.print("\n[bold]Recommended Images for Hop3 Testing[/]\n")
        table = Table()
        table.add_column("Image Name", style="cyan")
        table.add_column("Description")
        table.add_column("Notes")
        for image, desc, notes in RECOMMENDED_IMAGES:
            table.add_row(image, desc, notes)
        console.print(table)
        return

    extra_args = ["-v"] if verbose else []

    results = run_multi_distro_tests(
        images=list(images) if images else None,
        use_local_repo=use_local_repo,
        suites=suites,
        stop_on_failure=not continue_on_failure,
        extra_args=extra_args or None,
    )

    # Exit with appropriate code
    if any(not r.success for r in results):
        ctx.exit(1)
