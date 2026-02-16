#!/usr/bin/env python3
# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Hop3 Demo Launcher.

Run demos on a target server to showcase Hop3 deployment features.

Usage:
    python demos/demo.py --host HOST [options] [demos...]
    python demos/demo.py --help
    python demos/demo.py --list
    python demos/demo.py --inventory

Examples:
    python demos/demo.py --host 46.62.169.221                    # Run all demos
    python demos/demo.py --host 46.62.169.221 demo1              # Run demo1 only
    python demos/demo.py --host 46.62.169.221 --local demo1      # Use local code
    python demos/demo.py --host 46.62.169.221 --keep demo2       # Keep apps running
    python demos/demo.py --host 46.62.169.221 ~/my-app           # Run external app
"""

from __future__ import annotations

import sys
from pathlib import Path

# Setup import path - must be before any lib imports
DEMOS_DIR = Path(__file__).parent
if str(DEMOS_DIR) not in sys.path:
    sys.path.insert(0, str(DEMOS_DIR))

import contextlib
import secrets
import time

from lib.cli import create_parser
from lib.commands import set_debug_mode
from lib.context import DemoContext, OutputLevel
from lib.discovery import discover_demos, resolve_demo
from lib.display import list_demos, print_banner, print_config, show_inventory
from lib.logging import (
    end_demo_timing,
    get_log_session,
    get_timing_collector,
    init_logging,
    init_timing,
    start_demo_timing,
)
from lib.output import (
    pause,
    print_demo_result,
    print_error,
    print_header,
    print_info,
    print_summary_stats,
    print_success,
    print_warning,
    set_output_level,
)
from lib.phases import configure_cli, run_demo, run_prerequisites
from lib.results_db import get_results_db, record_demo_result


def main() -> int:
    """Main entry point."""
    parser = create_parser()

    # Handle --list before requiring --host
    if "--list" in sys.argv:
        demo_dirs = _extract_demo_dirs()
        list_demos(demo_dirs or None)
        return 0

    # Handle --inventory before requiring --host
    if "--inventory" in sys.argv:
        demo_dirs = _extract_demo_dirs()
        show_inventory(demo_dirs or None)
        return 0

    # Handle case where --host is not provided (required for SSH backend)
    is_docker_backend = "--backend" in sys.argv and "docker" in sys.argv
    is_docker_backend = is_docker_backend or ("-b" in sys.argv and "docker" in sys.argv)

    if not is_docker_backend:
        if "-H" not in sys.argv and "--host" not in sys.argv:
            if "-h" in sys.argv or "--help" in sys.argv:
                parser.print_help()
                return 0
            print_error(
                "Missing required argument: --host HOST (or use --backend docker)"
            )
            print_info("Run with --help for usage information")
            return 2

    args = parser.parse_args()

    # Determine output level
    output_level = _get_output_level(args)
    set_output_level(output_level)

    # Enable debug mode for hop3 commands if --debug flag is set
    if getattr(args, "debug", False):
        set_debug_mode(enabled=True)

    # Initialize logging (unless --no-logs)
    if not getattr(args, "no_logs", False):
        logs_dir = getattr(args, "logs_dir", None)
        log_session = init_logging(logs_dir)
        # Always show log directory, even in quiet mode
        print_info(f"Logs: {log_session.session_dir}")

    # Initialize timing instrumentation
    init_timing()

    # Determine host for results tracking
    results_host = getattr(args, "host", None) or "docker"

    # Handle --clear-results
    if getattr(args, "clear_results", False):
        db = get_results_db()
        cleared = db.clear_host(results_host)
        print_info(f"Cleared {cleared} stored results for host '{results_host}'")

    # Discover and resolve demos
    available_demos = discover_demos(args.demo_dirs)
    demos_to_run = _resolve_demos(args, available_demos, results_host)
    if demos_to_run is None:
        return 2

    # Handle quick mode with all tests passing (empty list, not an error)
    if not demos_to_run:
        return 0

    # Enforce single demo with --keep (since all demos share the same hostname)
    if args.no_cleanup and len(demos_to_run) > 1:
        print_error("--keep requires a single demo (all demos share the same hostname)")
        print_info("Specify a single demo or remove --keep")
        return 2

    # Create context
    ctx = _create_context(args, output_level)

    # Print banner and config
    print_banner(output_level)
    demo_names = [name for name, _, _ in demos_to_run]
    print_config(ctx, demo_names)

    # Run phases
    return _run_all_phases(ctx, demos_to_run, results_host)


def _extract_demo_dirs() -> list[Path]:
    """Extract --demo-dir arguments from sys.argv."""
    demo_dirs = []
    args_iter = iter(sys.argv[1:])
    for arg in args_iter:
        if arg == "--demo-dir":
            with contextlib.suppress(StopIteration):
                demo_dirs.append(Path(next(args_iter)))
    return demo_dirs


def _get_output_level(args) -> OutputLevel:
    """Determine output level from arguments."""
    if args.silent:
        return OutputLevel.SILENT
    if args.quiet:
        return OutputLevel.QUIET
    if args.verbose or getattr(args, "debug", False):
        return OutputLevel.VERBOSE
    return OutputLevel.NORMAL


def _resolve_demos(
    args, available_demos, results_host: str
) -> list[tuple[str, Path, bool]] | None:
    """Resolve demo arguments to paths.

    Args:
        args: Parsed command-line arguments
        available_demos: Dict of discovered demos
        results_host: Host identifier for results database

    Returns:
        List of (name, path, is_generic) tuples, or None on error.
    """
    demo_args = args.demos or []

    # Handle 'all' keyword or empty list
    if not demo_args or (len(demo_args) == 1 and demo_args[0].lower() == "all"):
        demo_args = list(available_demos.keys())
        if not demo_args:
            print_error("No built-in demos found in demos/ directory")
            return None

    # Handle --quick flag: filter to only failing/untested demos
    if getattr(args, "quick", False):
        db = get_results_db()
        demos_to_rerun = db.get_demos_to_rerun(demo_args, results_host)

        if not demos_to_rerun:
            print_success("All demos passed in previous run. Nothing to re-run.")
            summary = db.get_summary(results_host)
            print_info(
                f"  Previous results: {summary['pass']} passed, "
                f"{summary['fail']} failed, {summary['skip']} skipped"
            )
            return []

        skipped_count = len(demo_args) - len(demos_to_rerun)
        if skipped_count > 0:
            print_info(
                f"Quick mode: running {len(demos_to_rerun)} demos "
                f"(skipping {skipped_count} that passed previously)"
            )

        # Show which demos will be run
        failing = set(db.get_failing_demos(results_host))
        untested = set(db.get_untested_demos(demo_args, results_host))
        for name in demos_to_rerun:
            if name in failing:
                print_info(f"  - {name} (failed)")
            elif name in untested:
                print_info(f"  - {name} (new)")

        demo_args = demos_to_rerun

    # Resolve all demo arguments
    demos_to_run: list[tuple[str, Path, bool]] = []
    for demo_arg in demo_args:
        if demo_arg.lower() == "all":
            continue

        name, demo_dir, is_generic = resolve_demo(demo_arg, args.demo_dirs)
        if demo_dir is None:
            print_error(f"Demo not found: '{demo_arg}'")
            print_info("Use --list to see available built-in demos")
            print_info("Or specify a path to a Hop3 application directory")
            return None

        demos_to_run.append((name, demo_dir, is_generic))

    if not demos_to_run:
        # This is OK in quick mode - all tests passed
        if getattr(args, "quick", False):
            return []
        print_error("No valid demos specified")
        return None

    return demos_to_run


def _create_context(args, output_level: OutputLevel) -> DemoContext:
    """Create the demo context from arguments."""
    admin_password = args.admin_password or secrets.token_urlsafe(16)
    backend = getattr(args, "backend", "ssh")

    # For Docker mode, set appropriate defaults for server_ip and admin_domain
    if backend == "docker":
        server_ip = "localhost"
        admin_domain = args.admin_domain or "hop3.dev"
    else:
        server_ip = getattr(args, "host", "") or ""
        admin_domain = args.admin_domain

    return DemoContext(
        backend=backend,
        server_ip=server_ip,
        ssh_user=args.ssh_user,
        docker_image=getattr(args, "docker_image", "ubuntu:24.04"),
        docker_container=getattr(args, "docker_container", "hop3-demo"),
        admin_domain=admin_domain,
        admin_user=args.admin_user,
        admin_email=args.admin_email,
        admin_password=admin_password,
        pause_between_steps=args.pause,
        skip_install=args.skip_install,
        preflight=getattr(args, "preflight", False),
        no_cleanup=args.no_cleanup,
        use_local_code=args.use_local_code,
        clean_before=getattr(args, "clean_before", False),
        fail_fast=getattr(args, "fail_fast", False),
        verbose=args.verbose,
        debug=getattr(args, "debug", False),
        output_level=output_level,
    )


def _run_all_phases(
    ctx: DemoContext, demos_to_run: list[tuple[str, Path, bool]], results_host: str
) -> int:
    """Run all demo phases.

    Args:
        ctx: Demo context
        demos_to_run: List of (name, path, is_generic) tuples
        results_host: Host identifier for storing results

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    overall_start = time.time()

    try:
        # Phase 1: Prerequisites
        if not run_prerequisites(ctx):
            return 1
        pause(ctx.pause_between_steps)

        # Phase 2: Configure CLI
        if not configure_cli(ctx):
            return 1
        pause(ctx.pause_between_steps)

        # Phase 3: Run demos
        results = []
        for name, demo_dir, is_generic in demos_to_run:
            # Start timing for this demo
            start_demo_timing(name)

            result = run_demo(ctx, name, demo_dir, is_generic=is_generic)
            results.append(result)

            # Record result to database immediately
            record_demo_result(result, results_host)

            # End timing and get summary
            timing_summary = end_demo_timing()
            if timing_summary and ctx.output_level >= OutputLevel.NORMAL:
                print()
                print(timing_summary)

            # Stop on first failure if --fail-fast is set
            if ctx.fail_fast and result.status == "fail":
                break

            pause(ctx.pause_between_steps)

        # Phase 4: Summary
        return _show_summary(ctx, results, overall_start, results_host)

    except KeyboardInterrupt:
        print()
        print_error("Demo interrupted by user")
        return 130


def _show_summary(
    ctx: DemoContext, results: list, overall_start: float, results_host: str
) -> int:
    """Show demo summary and return exit code."""
    overall_duration = time.time() - overall_start
    passed = sum(1 for r in results if r.status == "pass")
    failed = sum(1 for r in results if r.status == "fail")
    skipped = sum(1 for r in results if r.status == "skip")

    # In quiet mode, just add a blank line before results (no header)
    if ctx.output_level == OutputLevel.QUIET:
        print()
    else:
        print_header("Demo Summary", phase=True)

    for result in results:
        print_demo_result(
            result.name,
            result.title,
            result.status,
            result.duration,
            result.error,
        )

    print_summary_stats(passed, failed, skipped, overall_duration)

    # Always show log directory in summary
    log_session = get_log_session()
    if log_session:
        print()
        print_info(f"Detailed logs: {log_session.session_dir}")

    # Show timing summary
    timing_collector = get_timing_collector()
    if timing_collector:
        # Show setup phase timing if captured
        if timing_collector.setup_timings:
            print()
            print(timing_collector.setup_summary())
        # Show aggregate timing for multiple demos
        if len(timing_collector.demos) > 1:
            print()
            print(timing_collector.aggregate_summary())

    # Show admin credentials and UI URL if keeping apps
    if ctx.no_cleanup and ctx.output_level >= OutputLevel.NORMAL:
        print()
        print("  Admin credentials:")
        print(f"    Username: {ctx.admin_user}")
        print(f"    Password: {ctx.admin_password}")
        print()
        print("  Admin UI:")
        if ctx.admin_domain:
            print(f"    https://{ctx.admin_domain}/")
        else:
            print(f"    http://{ctx.server_ip}:8000/  (direct, unsecured)")
            print("    Tip: Use --admin-domain to enable secure HTTPS access")

    # Show quick mode hint if there were failures
    if failed > 0 and ctx.output_level >= OutputLevel.QUIET:
        print()
        print_info(
            f"Tip: Re-run with --quick to only retry the {failed} failed demo(s)"
        )

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
