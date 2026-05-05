#!/usr/bin/env python3
"""Sync version from top-level package to all subpackages.

Uses `uv version` to read and update versions across the workspace.
"""

import argparse
import subprocess
import sys

PACKAGES = [
    "hop3-cli",
    "hop3-installer",
    "hop3-rootd",
    "hop3-server",
    "hop3-testing",
    "hop3-tui",
]


class Error(Exception):
    pass


def run_uv_version(*args: str) -> str:
    """Run uv version with given arguments and return output."""
    cmd = ["uv", "version", *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise Error(f"Command failed: {' '.join(cmd)}\n{result.stderr}")
    return result.stdout.strip()


def get_root_version() -> str:
    """Read the version from the top-level package."""
    return run_uv_version("--short")


def get_package_version(package: str) -> str:
    """Read the version from a specific package."""
    return run_uv_version("--package", package, "--short")


def set_package_version(package: str, version: str, dry_run: bool = False) -> str:
    """Set the version for a specific package."""
    args = ["--package", package, version]
    if dry_run:
        args.append("--dry-run")
    return run_uv_version(*args)


def sync_versions(dry_run: bool = False):
    """Sync version from root package to all subpackages."""
    root_version = get_root_version()
    print(f"Root version: {root_version}")
    print()
    print("Syncing subpackages:")

    for package in PACKAGES:
        current_version = get_package_version(package)
        if current_version == root_version:
            print(f"  {package}: already at {root_version}")
        else:
            if dry_run:
                print(f"  {package}: {current_version} -> {root_version} (dry run)")
            else:
                set_package_version(package, root_version)
                print(f"  {package}: {current_version} -> {root_version}")

    print()
    print("Done." if not dry_run else "Done (dry run - no files modified).")


def bump_version(bump_type: str, dry_run: bool = False):
    """Bump the root version and sync to all subpackages."""
    # First bump the root version
    print(f"Bumping root version ({bump_type})...")
    args = ["--bump", bump_type]
    if dry_run:
        args.append("--dry-run")
    output = run_uv_version(*args)
    print(f"  {output}")
    print()

    # Get the new version
    if dry_run:
        # Parse from dry-run output: "hop3 0.4.0b3 => 0.4.1"
        new_version = output.split("=>")[-1].strip()
    else:
        new_version = get_root_version()

    # Sync to all packages
    print("Syncing subpackages:")
    for package in PACKAGES:
        current_version = get_package_version(package)
        if current_version == new_version:
            print(f"  {package}: already at {new_version}")
        else:
            if dry_run:
                print(f"  {package}: {current_version} -> {new_version} (dry run)")
            else:
                set_package_version(package, new_version)
                print(f"  {package}: {current_version} -> {new_version}")

    print()
    print("Done." if not dry_run else "Done (dry run - no files modified).")


def main():
    parser = argparse.ArgumentParser(
        description="Sync or bump version across all packages in the workspace."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without modifying files",
    )
    parser.add_argument(
        "--bump",
        choices=[
            "major",
            "minor",
            "patch",
            "stable",
            "alpha",
            "beta",
            "rc",
            "post",
            "dev",
        ],
        help="Bump the version using the given semantics before syncing",
    )
    args = parser.parse_args()

    try:
        if args.bump:
            bump_version(args.bump, args.dry_run)
        else:
            sync_versions(args.dry_run)
    except Error as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
