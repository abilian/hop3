#!/usr/bin/env python3
# Copyright (c) 2024-2025 Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Build all nix-apps locally to verify they work.

This script iterates over apps/nix-apps/ and runs nix-build on each one.
Useful for validating hop3.nix files before running the full test suite.

Usage:
    ./scripts/build-nix-apps.py
    ./scripts/build-nix-apps.py --app static-hello  # Build single app
    ./scripts/build-nix-apps.py --debug             # Show full error output
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Find project root
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
NIX_APPS_DIR = PROJECT_ROOT / "apps" / "nix-apps"


def build_app(app_dir: Path, show_trace: bool = False) -> tuple[bool, str, str]:
    """Build a single nix app.

    Args:
        app_dir: Path to the app directory containing hop3.nix
        show_trace: Whether to run with --show-trace for detailed errors

    Returns:
        Tuple of (success, short_message, full_stderr)
    """
    nix_file = app_dir / "hop3.nix"
    if not nix_file.exists():
        return False, "no hop3.nix found", ""

    cmd = ["nix-build", str(nix_file), "-A", "package", "--no-out-link"]
    if show_trace:
        cmd.append("--show-trace")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=app_dir,
    )

    full_stderr = result.stderr.strip()

    if result.returncode == 0:
        store_path = result.stdout.strip()
        return True, store_path, ""
    else:
        # Extract the key error message from stderr
        lines = full_stderr.split("\n")

        # Find the LAST "error:" line (most specific)
        last_error = None
        last_error_idx = -1
        for i, line in enumerate(lines):
            if line.strip().startswith("error:"):
                last_error = line.strip()
                last_error_idx = i

        if last_error:
            msg = last_error[6:].strip()  # Remove "error:" prefix
            # If message is empty, check next line
            if not msg and last_error_idx + 1 < len(lines):
                msg = lines[last_error_idx + 1].strip()
            return False, msg if msg else "build error", full_stderr

        # Fallback: return last non-empty line
        for line in reversed(lines):
            if line.strip():
                return False, line.strip()[:100], full_stderr

        return False, "build failed (no error message)", full_stderr


def main():
    parser = argparse.ArgumentParser(description="Build nix-apps locally")
    parser.add_argument("--app", help="Build only this app")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show store paths")
    parser.add_argument("--debug", "-d", action="store_true",
                        help="Show full nix output for failed builds")
    parser.add_argument("--show-trace", action="store_true",
                        help="Run nix-build with --show-trace")
    args = parser.parse_args()

    if not NIX_APPS_DIR.exists():
        print(f"Error: {NIX_APPS_DIR} not found")
        sys.exit(1)

    # Check nix is available
    result = subprocess.run(["nix", "--version"], capture_output=True)
    if result.returncode != 0:
        print("Error: nix is not installed or not in PATH")
        sys.exit(1)

    # Get apps to build
    if args.app:
        app_dirs = [NIX_APPS_DIR / args.app]
        if not app_dirs[0].exists():
            print(f"Error: App '{args.app}' not found in {NIX_APPS_DIR}")
            sys.exit(1)
    else:
        app_dirs = sorted([d for d in NIX_APPS_DIR.iterdir() if d.is_dir()])

    print(f"Building {len(app_dirs)} nix apps...\n")

    passed = 0
    failed = 0
    results = []

    for app_dir in app_dirs:
        app_name = app_dir.name
        print(f"[{app_name}] ", end="", flush=True)

        success, message, full_stderr = build_app(app_dir, show_trace=args.show_trace)

        if success:
            passed += 1
            print("PASS")
            if args.verbose:
                print(f"  -> {message}")
            results.append((app_name, True, message, ""))
        else:
            failed += 1
            print("FAIL")
            print(f"  -> {message}")
            if args.debug and full_stderr:
                print("\n  --- Full nix output ---")
                for line in full_stderr.split("\n"):
                    print(f"  {line}")
                print("  --- End of output ---\n")
            results.append((app_name, False, message, full_stderr))

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed out of {len(app_dirs)}")
    print("=" * 60)

    if failed > 0:
        print("\nFailed apps:")
        for name, success, message, _ in results:
            if not success:
                print(f"  - {name}: {message}")

        if not args.debug:
            print("\nTip: Use --debug to see full nix output for failed builds")
            print("     Use --show-trace for detailed nix stack traces")

        sys.exit(1)


if __name__ == "__main__":
    main()
