# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Matrix command: run E2E tests on cloud infrastructure (ADR 052 D9).

Canonical name is `matrix` (multi-distro across cloud images); `cloud` stays
registered as a deprecated alias. Supports multiple cloud providers (Hetzner
Cloud by default). Merges the former 'hetzner' and 'multi-distro' commands.
"""

from __future__ import annotations

import sys

import click

from hop3_testing.cli.deprecation import warn_deprecated


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
    with_features: str | None,
    verbose: bool,
) -> list[str]:
    """Build argv list for daily CLI."""
    argv = ["daily-test", "run"]

    options = [
        (server_id, "--server-id", str(server_id) if server_id else None),
        (branch != "devel", "--branch", branch),
        (image, "--image", image),
        (config_file, "--config", config_file),
        (report_dir != "./reports", "--report-dir", report_dir),
        (local_repo_path, "--local-repo-path", local_repo_path),
        (with_features, "--with", with_features),
    ]
    for condition, flag, value in options:
        if condition and value:
            argv.extend([flag, value])

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

    for suite in suites:
        argv.extend(["--suites", suite])

    return argv


def _normalize_paths(paths: tuple[str, ...]) -> tuple[str, ...]:
    """Normalize app directory paths (strip trailing slashes)."""
    if not paths:
        return ()
    return tuple(p.rstrip("/") for p in paths)


@click.command("matrix")
# Provider
@click.option(
    "--provider",
    type=click.Choice(["hetzner"]),
    default="hetzner",
    help="Cloud provider (default: hetzner)",
)
# Image selection (mutually exclusive single vs multi)
@click.option("--image", default=None, help="Single OS image (e.g., ubuntu-24.04)")
@click.option(
    "--images",
    default=None,
    help="Comma-separated images or 'all' (e.g., ubuntu-24.04,debian-13)",
)
@click.option("--list-images", is_flag=True, help="List available OS images")
# Server
@click.option("--server-id", type=int, help="Cloud server ID to test on")
@click.option("--branch", default="devel", help="Git branch to test")
@click.option("--config", "config_file", type=click.Path(), help="Config file path")
@click.option(
    "--report-dir",
    type=click.Path(),
    default="./reports",
    help="Directory for reports",
)
# Phase control
@click.option("--skip-reset", is_flag=True, help="Skip server reset")
@click.option("--skip-deploy", is_flag=True, help="Skip Hop3 deployment")
@click.option("--skip-tests", is_flag=True, help="Skip test execution")
# Test options
@click.option(
    "--apps",
    multiple=True,
    help="App directories to test (e.g., apps/test-apps, demos). Default: apps/test-apps",
)
@click.option("-x", "--fail-fast", is_flag=True, help="Stop on first failure")
@click.option("--random", "random_order", is_flag=True, help="Random test order")
@click.option("--use-local-repo/--no-local-repo", default=True, help="Use local repo")
@click.option("--local-repo-path", type=click.Path(), help="Path to local Hop3 repo")
@click.option(
    "--with",
    "with_features",
    default=None,
    help=(
        "Comma-separated server features/addons to install on top of the "
        "baseline (docker,mysql,postgresql), e.g. '--with redis'. Needed for "
        "apps whose hop3.toml declares those addons."
    ),
)
@click.option("-v", "--verbose", is_flag=True, help="Verbose output")
@click.pass_context
def matrix_test(
    ctx: click.Context,
    provider: str,
    image: str | None,
    images: str | None,
    list_images: bool,
    server_id: int | None,
    branch: str,
    config_file: str | None,
    report_dir: str,
    skip_reset: bool,
    skip_deploy: bool,
    skip_tests: bool,
    apps: tuple[str, ...],
    fail_fast: bool,
    random_order: bool,
    use_local_repo: bool,
    local_repo_path: str | None,
    with_features: str | None,
    verbose: bool,
) -> None:
    """Run E2E tests on cloud infrastructure (a distro matrix).

    Tests Hop3 on real cloud servers. Supports single-image and
    multi-distribution testing.

    \b
    Examples:
      hop3-test matrix --images ubuntu-24.04,debian-13   # Multiple distros
      hop3-test matrix --images all                      # All distros
      hop3-test matrix --image ubuntu-24.04              # Single distro
      hop3-test matrix --list-images                     # Available images
      hop3-test matrix --apps apps/test-apps --apps demos  # Specific dirs
      hop3-test matrix --skip-reset --skip-deploy        # Only run tests

    Requires HETZNER_API_TOKEN environment variable (for Hetzner provider).
    """
    # ADR 052 D9: `cloud` is a deprecated alias for `matrix` (still works).
    if ctx.info_name == "cloud":
        warn_deprecated("cloud", "matrix", kind="command")

    # Convert --apps paths to suite names for the underlying system
    # e.g., "apps/test-apps" -> "apps/test-apps-procfile", "demos" -> "demos"
    suites = _normalize_paths(apps)

    # List images mode
    if list_images:
        _show_images(provider)
        return

    # Multi-distro mode (--images)
    if images:
        _run_multi_distro(
            provider=provider,
            images_str=images,
            suites=suites[0] if suites else "apps/test-apps-procfile",
            use_local_repo=use_local_repo,
            fail_fast=fail_fast,
            verbose=verbose,
            with_features=with_features,
            ctx=ctx,
        )
        return

    # Single-image mode (default)
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
        with_features,
        verbose,
    )

    from hop3_testing.system_tests.hetzner_cli import main  # noqa: PLC0415

    old_argv = sys.argv
    try:
        sys.argv = argv
        main()
    finally:
        sys.argv = old_argv


def _show_images(provider: str) -> None:
    """Show available OS images for a provider."""
    from rich.console import Console  # noqa: PLC0415
    from rich.table import Table  # noqa: PLC0415

    from hop3_testing.system_tests.multi_distro import (  # noqa: PLC0415
        HETZNER_IMAGES,
    )

    # For now only Hetzner; when adding providers, dispatch here
    image_list = HETZNER_IMAGES

    console = Console()
    console.print(f"\n[bold]Available OS images ({provider})[/]\n")
    table = Table()
    table.add_column("Image Name", style="cyan")
    table.add_column("Description")
    table.add_column("Notes")
    for img_name, desc, notes in image_list:
        table.add_row(img_name, desc, notes)
    console.print(table)


def _run_multi_distro(
    *,
    provider: str,
    images_str: str,
    suites: str,
    use_local_repo: bool,
    fail_fast: bool,
    verbose: bool,
    with_features: str | None,
    ctx: click.Context,
) -> None:
    """Run tests across multiple distributions."""
    from hop3_testing.system_tests.multi_distro import (  # noqa: PLC0415
        HETZNER_IMAGES,
        run_multi_distro_tests,
    )

    # Resolve "all" to the full image list for this provider
    if images_str == "all":
        image_list = [img[0] for img in HETZNER_IMAGES]
    else:
        image_list = [img.strip() for img in images_str.split(",") if img.strip()]

    extra_args = ["-v"] if verbose else []
    if with_features:
        extra_args.extend(["--with", with_features])

    results = run_multi_distro_tests(
        images=image_list,
        use_local_repo=use_local_repo,
        suites=suites,
        stop_on_failure=fail_fast,
        extra_args=extra_args or None,
    )

    if any(not r.success for r in results):
        ctx.exit(1)
