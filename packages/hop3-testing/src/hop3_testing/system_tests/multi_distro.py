# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Multi-distribution test runner.

Runs the test suite across multiple Linux distributions, stopping on first failure.
"""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass

from rich.console import Console
from rich.table import Table

# Hetzner Cloud images supported for Hop3 testing
# Image names must match Hetzner Cloud image identifiers
HETZNER_IMAGES = [
    ("ubuntu-24.04", "Ubuntu 24.04 LTS", "Default, well-tested"),
    ("debian-13", "Debian 13 (trixie)", "Stable, supported"),
    ("debian-12", "Debian 12 (bookworm)", "Older stable"),
    ("fedora-42", "Fedora 42", "Latest Fedora"),
    ("rocky-9", "Rocky Linux 9", "RHEL-compatible"),
    ("alma-9", "AlmaLinux 9", "RHEL-compatible"),
]


def show_images(provider: str) -> None:
    """Print the OS images available for a provider (`run --list-images`)."""
    console = Console()
    console.print(f"\n[bold]Available OS images ({provider})[/]\n")
    table = Table()
    table.add_column("Image Name", style="cyan")
    table.add_column("Description")
    table.add_column("Notes")
    for img_name, desc, notes in HETZNER_IMAGES:  # only Hetzner today
        table.add_row(img_name, desc, notes)
    console.print(table)


@dataclass
class TestResult:
    """Result of a single distro test run."""

    image: str
    success: bool
    duration: float
    error: str | None = None


def run_test_for_image(
    image: str,
    console: Console,
    *,
    app_names: tuple[str, ...] = ("apps/test-apps-procfile",),
    source: str = "local",
    branch: str = "devel",
    extra_args: list[str] | None = None,
    verbose: bool = False,
) -> TestResult:
    """
    Run test suite for a specific image.

    Args:
        image: Image name (e.g., "ubuntu-24.04").
        console: Rich console for output.
        app_names: App names/paths, passed as `run`'s positional args.
        source: Install source for `run --from` (local | git | pypi).
        branch: Git branch (used when source == "git").
        extra_args: Additional arguments to pass (e.g. repeated --with).
        verbose: Emit the group-level -v before the `run` subcommand.

    Returns:
        TestResult with success status and duration.
    """
    # ADR 052 7b.7: each sweep leg is a full `hop3-test run --provider hetzner`,
    # so it provisions + deploys + tests + PERSISTS to the shared result store
    # (server_id/token inherited via HETZNER_* env; HOP3_TEST_RESULTS_DB too).
    cmd = [sys.executable, "-m", "hop3_testing.cli"]
    if verbose:
        cmd.append("-v")  # group-level flag, must precede the `run` subcommand
    cmd += ["run", "--provider", "hetzner", "--image", image, "--from", source]
    if source == "git":
        cmd += ["--branch", branch]
    cmd += list(app_names)  # positional app-names, mirrors `run`

    if extra_args:
        cmd.extend(extra_args)

    console.print(f"\n[bold blue]{'=' * 70}[/]")
    console.print(f"[bold blue]Testing: {image}[/]")
    console.print(f"[bold blue]{'=' * 70}[/]\n")

    start_time = time.time()

    try:
        result = subprocess.run(
            cmd,
            check=False,
            cwd=None,  # Use current directory
        )
        duration = time.time() - start_time

        if result.returncode == 0:
            return TestResult(image=image, success=True, duration=duration)

        return TestResult(
            image=image,
            success=False,
            duration=duration,
            error=f"Exit code: {result.returncode}",
        )

    except Exception as e:
        duration = time.time() - start_time
        return TestResult(
            image=image,
            success=False,
            duration=duration,
            error=str(e),
        )


def _print_summary(
    console: Console,
    results: list[TestResult],
    images: list[str],
    total_duration: float,
) -> None:
    """Print test summary table."""
    console.print("\n")
    console.print("[bold]" + "=" * 70 + "[/]")
    console.print("[bold]SUMMARY[/]")
    console.print("[bold]" + "=" * 70 + "[/]")

    table = Table()
    table.add_column("Image", style="cyan")
    table.add_column("Status")
    table.add_column("Duration", justify="right")
    table.add_column("Notes")

    passed = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)

    for result in results:
        status = "[green]PASSED[/]" if result.success else "[red]FAILED[/]"
        duration = f"{result.duration:.1f}s"
        notes = result.error or ""
        table.add_row(result.image, status, duration, notes)

    console.print(table)

    not_tested = len(images) - len(results)
    if not_tested > 0:
        console.print(f"\n[yellow]Not tested: {not_tested} image(s)[/]")

    console.print(f"\nTotal: {passed} passed, {failed} failed")
    console.print(f"Total duration: {total_duration:.1f}s")

    if failed > 0:
        console.print("\n[bold red]OVERALL: FAILED[/]")
    else:
        console.print("\n[bold green]OVERALL: PASSED[/]")


def run_multi_distro_tests(
    images: list[str] | None = None,
    *,
    app_names: tuple[str, ...] = ("apps/test-apps-procfile",),
    source: str = "local",
    branch: str = "devel",
    stop_on_failure: bool = True,
    verbose: bool = False,
    extra_args: list[str] | None = None,
) -> list[TestResult]:
    """
    Run tests across multiple distributions.

    Args:
        images: List of images to test. Uses HETZNER_IMAGES if None.
        app_names: App names/paths, passed as `run`'s positional args.
        source: Install source for `run --from` (local | git | pypi).
        branch: Git branch (used when source == "git").
        stop_on_failure: Stop on first failure.
        extra_args: Additional arguments to pass (e.g. repeated --with).

    Returns:
        List of TestResult objects.
    """
    console = Console()

    if images is None:
        images = [img[0] for img in HETZNER_IMAGES]

    results: list[TestResult] = []
    total_start = time.time()

    console.print("\n[bold green]Multi-Distribution Test Runner[/]")
    console.print(f"Images to test: {', '.join(images)}")
    console.print(f"Apps: {', '.join(app_names)}")
    console.print(f"Stop on failure: {stop_on_failure}")
    console.print()

    for image in images:
        result = run_test_for_image(
            image=image,
            console=console,
            app_names=app_names,
            source=source,
            branch=branch,
            extra_args=extra_args,
            verbose=verbose,
        )
        results.append(result)

        if result.success:
            console.print(f"\n[bold green]PASSED[/]: {image} ({result.duration:.1f}s)")
        else:
            console.print(f"\n[bold red]FAILED[/]: {image} ({result.duration:.1f}s)")
            if result.error:
                console.print(f"  Error: {result.error}")

            if stop_on_failure:
                console.print("\n[bold red]Stopping due to failure.[/]")
                break

    total_duration = time.time() - total_start
    _print_summary(console, results, images, total_duration)

    return results
