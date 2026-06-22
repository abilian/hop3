#!/usr/bin/env python3
"""Check all Hop3 tutorials using validoc.

This script validates and optionally runs all tutorial markdown files
organized by language subdirectory.

Usage:
    ./check.py              # Check syntax only (fast)
    ./check.py --run        # Check syntax then run all tutorials
    ./check.py --run python # Run only Python tutorials
    ./check.py --list       # List all tutorials
"""

import argparse
import subprocess
import sys
from pathlib import Path

# Tutorial directory structure
TUTORIALS_DIR = Path(__file__).parent
LANGUAGES = [
    "python",
    "javascript",
    "ruby",
    "php",
    "java",
    "go",
    "rust",
    "elixir",
    "dotnet",
]


def get_tutorials(language: str | None = None) -> list[Path]:
    """Get all tutorial markdown files, optionally filtered by language."""
    tutorials = []

    if language:
        lang_dir = TUTORIALS_DIR / language
        if lang_dir.is_dir():
            tutorials.extend(sorted(lang_dir.glob("*.md")))
    else:
        for lang in LANGUAGES:
            lang_dir = TUTORIALS_DIR / lang
            if lang_dir.is_dir():
                tutorials.extend(sorted(lang_dir.glob("*.md")))

    return tutorials


def run_validoc(command: str, tutorial: Path) -> bool:
    """Run validoc with the given command on a tutorial file."""
    cmd = ["validoc", command, str(tutorial)]
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode == 0


def check_tutorials(tutorials: list[Path]) -> tuple[list[Path], list[Path]]:
    """Run 'validoc check' on all tutorials."""
    passed = []
    failed = []

    print("=" * 60)
    print("PHASE 1: Syntax Check (validoc check)")
    print("=" * 60)
    print()

    for tutorial in tutorials:
        relative = tutorial.relative_to(TUTORIALS_DIR)
        print(f"Checking {relative}...", end=" ", flush=True)

        if run_validoc("check", tutorial):
            print("OK")
            passed.append(tutorial)
        else:
            print("FAILED")
            failed.append(tutorial)

    print()
    print(f"Check results: {len(passed)} passed, {len(failed)} failed")
    print()

    return passed, failed


def run_tutorials(tutorials: list[Path]) -> tuple[list[Path], list[Path]]:
    """Run 'validoc run' on all tutorials."""
    passed = []
    failed = []

    print("=" * 60)
    print("PHASE 2: Execute Tutorials (validoc run)")
    print("=" * 60)
    print()

    for tutorial in tutorials:
        relative = tutorial.relative_to(TUTORIALS_DIR)
        print(f"\n{'=' * 60}")
        print(f"Running {relative}")
        print("=" * 60)

        if run_validoc("run", tutorial):
            print(f"PASSED: {relative}")
            passed.append(tutorial)
        else:
            print(f"FAILED: {relative}")
            failed.append(tutorial)

    print()
    print("=" * 60)
    print(f"Run results: {len(passed)} passed, {len(failed)} failed")
    print("=" * 60)

    return passed, failed


def list_tutorials(tutorials: list[Path]) -> None:
    """List all tutorials grouped by language."""
    print("Available tutorials:")
    print()

    current_lang = None
    for tutorial in tutorials:
        lang = tutorial.parent.name
        if lang != current_lang:
            print(f"\n{lang.upper()}:")
            current_lang = lang
        print(f"  - {tutorial.name}")

    print()
    print(f"Total: {len(tutorials)} tutorials")


def main():
    parser = argparse.ArgumentParser(
        description="Check and run Hop3 tutorials using validoc"
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Run tutorials after checking syntax",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all tutorials without running",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check syntax, don't run (default behavior)",
    )
    parser.add_argument(
        "language",
        nargs="?",
        choices=LANGUAGES,
        help="Filter by language (e.g., python, javascript)",
    )

    args = parser.parse_args()

    # Get tutorials
    tutorials = get_tutorials(args.language)

    if not tutorials:
        print("No tutorials found!")
        if args.language:
            print(f"Check that {TUTORIALS_DIR / args.language} exists and contains .md files")
        sys.exit(1)

    # List mode
    if args.list:
        list_tutorials(tutorials)
        sys.exit(0)

    # Check syntax first
    check_passed, check_failed = check_tutorials(tutorials)

    if check_failed:
        print("Some tutorials failed syntax check. Fix these before running:")
        for t in check_failed:
            print(f"  - {t.relative_to(TUTORIALS_DIR)}")
        sys.exit(1)

    # Run tutorials if requested
    if args.run:
        run_passed, run_failed = run_tutorials(check_passed)

        if run_failed:
            print("\nFailed tutorials:")
            for t in run_failed:
                print(f"  - {t.relative_to(TUTORIALS_DIR)}")
            sys.exit(1)

    print("\nAll checks passed!")
    sys.exit(0)


if __name__ == "__main__":
    main()
