# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Multi-distribution test runner.

Runs the test suite across multiple Linux distributions, stopping on first failure.
"""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass

from rich.console import Console
from rich.table import Table

# Recommended images for Hop3 testing
# Note: Image names must match what's available on Hetzner Cloud
RECOMMENDED_IMAGES = [
    ("ubuntu-24.04", "Ubuntu 24.04 LTS", "Default, well-tested"),
    ("debian-13", "Debian 13 (trixie)", "Stable, supported"),
    ("debian-12", "Debian 12 (bookworm)", "Older stable"),
    ("fedora-42", "Fedora 42", "Latest Fedora"),
    ("rocky-9", "Rocky Linux 9", "RHEL-compatible"),
    ("alma-9", "AlmaLinux 9", "RHEL-compatible"),
]


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
    use_local_repo: bool = True,
    suites: str = "test-apps",
    extra_args: list[str] | None = None,
) -> TestResult:
    """Run test suite for a specific image.

    Args:
        image: Image name (e.g., "ubuntu-24.04").
        console: Rich console for output.
        use_local_repo: Whether to use local repository.
        suites: Test suites to run.
        extra_args: Additional arguments to pass.

    Returns:
        TestResult with success status and duration.
    """
    cmd = [
        sys.executable,
        "-m",
        "hop3_system_tests.cli",
        "run",
        "--image",
        image,
        "--suites",
        suites,
    ]

    if use_local_repo:
        cmd.append("--use-local-repo")

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
    use_local_repo: bool = True,
    suites: str = "test-apps",
    stop_on_failure: bool = True,
    extra_args: list[str] | None = None,
) -> list[TestResult]:
    """Run tests across multiple distributions.

    Args:
        images: List of images to test. Uses RECOMMENDED_IMAGES if None.
        use_local_repo: Whether to use local repository.
        suites: Test suites to run.
        stop_on_failure: Stop on first failure.
        extra_args: Additional arguments to pass.

    Returns:
        List of TestResult objects.
    """
    console = Console()

    if images is None:
        images = [img[0] for img in RECOMMENDED_IMAGES]

    results: list[TestResult] = []
    total_start = time.time()

    console.print("\n[bold green]Multi-Distribution Test Runner[/]")
    console.print(f"Images to test: {', '.join(images)}")
    console.print(f"Suites: {suites}")
    console.print(f"Stop on failure: {stop_on_failure}")
    console.print()

    for image in images:
        result = run_test_for_image(
            image=image,
            console=console,
            use_local_repo=use_local_repo,
            suites=suites,
            extra_args=extra_args,
        )
        results.append(result)

        if result.success:
            console.print(
                f"\n[bold green]PASSED[/]: {image} ({result.duration:.1f}s)"
            )
        else:
            console.print(
                f"\n[bold red]FAILED[/]: {image} ({result.duration:.1f}s)"
            )
            if result.error:
                console.print(f"  Error: {result.error}")

            if stop_on_failure:
                console.print("\n[bold red]Stopping due to failure.[/]")
                break

    total_duration = time.time() - total_start
    _print_summary(console, results, images, total_duration)

    return results


def main() -> int:
    """CLI entry point for multi-distro testing."""
    # Import here to avoid loading argparse when module is imported as library
    import argparse  # noqa: PLC0415

    parser = argparse.ArgumentParser(
        description="Run Hop3 tests across multiple Linux distributions."
    )
    parser.add_argument(
        "--images",
        nargs="+",
        default=None,
        help="Images to test (default: all recommended images).",
    )
    parser.add_argument(
        "--suites",
        default="test-apps",
        help="Test suites to run (default: test-apps).",
    )
    parser.add_argument(
        "--use-local-repo",
        action="store_true",
        default=True,
        help="Use local repository (default: True).",
    )
    parser.add_argument(
        "--no-local-repo",
        action="store_true",
        help="Don't use local repository.",
    )
    parser.add_argument(
        "--continue-on-failure",
        action="store_true",
        help="Continue testing even after a failure.",
    )
    parser.add_argument(
        "--list-images",
        action="store_true",
        help="List recommended images and exit.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output.",
    )

    args, extra_args = parser.parse_known_args()

    console = Console()

    if args.list_images:
        console.print("\n[bold]Recommended Images for Hop3 Testing[/]\n")
        table = Table()
        table.add_column("Image Name", style="cyan")
        table.add_column("Description")
        table.add_column("Notes")
        for image, desc, notes in RECOMMENDED_IMAGES:
            table.add_row(image, desc, notes)
        console.print(table)
        return 0

    use_local_repo = args.use_local_repo and not args.no_local_repo

    # Add verbose flag if specified
    if args.verbose and "-v" not in extra_args and "--verbose" not in extra_args:
        extra_args.append("-v")

    results = run_multi_distro_tests(
        images=args.images,
        use_local_repo=use_local_repo,
        suites=args.suites,
        stop_on_failure=not args.continue_on_failure,
        extra_args=extra_args or None,
    )

    # Return non-zero if any test failed
    if any(not r.success for r in results):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
