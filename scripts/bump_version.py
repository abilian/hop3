#!/usr/bin/env python3
"""Sync version from top-level package to all subpackages.

Reads the version from the top-level pyproject.toml and applies it
to all packages/*/pyproject.toml files.
"""

import glob
import sys
from pathlib import Path

import tomlkit
from tomlkit.exceptions import TOMLKitError


class Error(Exception):
    pass


def get_root_version() -> str:
    """Read the version from the top-level pyproject.toml."""
    try:
        pyproject = Path("pyproject.toml").read_text()
        doc = tomlkit.parse(pyproject)
        return doc["project"]["version"]
    except FileNotFoundError as e:
        msg = f"Error reading pyproject.toml: {e}"
        raise Error(msg) from e
    except (TOMLKitError, KeyError) as e:
        msg = f"Error parsing pyproject.toml: {e}"
        raise Error(msg) from e


def update_version_in_file(file_path: str, new_version: str, dry_run: bool = False):
    """Update the version in a single pyproject.toml file."""
    try:
        pyproject_content = Path(file_path).read_text()
        doc = tomlkit.parse(pyproject_content)

        if "project" not in doc or "version" not in doc["project"]:
            print(f"Warning: 'project.version' not found in {file_path}. Skipping.")
            return

        current_version = doc["project"]["version"]
        if current_version == new_version:
            print(f"  {file_path}: already at {new_version}")
            return

        if dry_run:
            print(f"  {file_path}: {current_version} -> {new_version} (dry run)")
        else:
            doc["project"]["version"] = new_version
            with open(file_path, "w") as f:
                tomlkit.dump(doc, f)
            print(f"  {file_path}: {current_version} -> {new_version}")

    except FileNotFoundError:
        msg = f"Error: File not found: {file_path}"
        raise Error(msg) from None
    except (TOMLKitError, KeyError) as e:
        msg = f"Error parsing {file_path}: {e}"
        raise Error(msg) from e


def sync_versions(dry_run: bool = False):
    """Sync version from root package to all subpackages."""
    root_version = get_root_version()
    print(f"Root version: {root_version}")
    print()
    print("Syncing subpackages:")

    package_files = sorted(glob.glob("packages/*/pyproject.toml"))
    if not package_files:
        print("  No subpackages found in packages/*/")
        return

    for file_path in package_files:
        update_version_in_file(file_path, root_version, dry_run)

    print()
    print("Done." if not dry_run else "Done (dry run - no files modified).")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Sync version from root package to all subpackages."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without modifying files",
    )
    args = parser.parse_args()

    try:
        sync_versions(args.dry_run)
    except Error as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
