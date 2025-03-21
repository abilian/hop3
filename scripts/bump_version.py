#!/usr/bin/env python3

import argparse
import glob
import sys
from pathlib import Path

import tomlkit
from tomlkit.exceptions import TOMLKitError


def bump_version(bump_type: str, dry_run: bool = False):
    """Bumps the version in pyproject.toml and all packages/*/pyproject.toml.

    Args:
        bump_type: The type of version bump ('patch', 'minor', or 'major').
        dry_run: If True, print the changes without actually modifying files.
    """

    current_version = get_current_version()
    new_version_str = calculate_new_version(bump_type, current_version)
    update_version_in_file("pyproject.toml", new_version_str, dry_run)

    package_files = glob.glob("packages/*/pyproject.toml")
    for file_path in package_files:
        update_version_in_file(file_path, new_version_str, dry_run)

    print("Version bumping complete.")


class Error(Exception):
    pass


def get_current_version() -> list[int]:
    try:
        pyproject = Path("pyproject.toml").read_text()
        doc = tomlkit.parse(pyproject)
        current_version_str = doc["project"]["version"]
        current_version = list(map(int, current_version_str.split(".")))
        return current_version
    except FileNotFoundError as e:
        msg = f"Error reading pyproject.toml: {e}"
        raise Error(msg)
    except (TOMLKitError, KeyError) as e:
        msg = f"Error parsing pyproject.toml: {e}"
        raise Error(msg)
    except ValueError:
        msg = (
            "Error: Invalid version format in pyproject.toml.  Expected format: x.y.z"
        )
        raise Error(msg)


def calculate_new_version(bump_type, current_version):
    if bump_type == "patch":
        current_version[2] += 1
    elif bump_type == "minor":
        current_version[1] += 1
        current_version[2] = 0  # Reset patch
    elif bump_type == "major":
        current_version[0] += 1
        current_version[1] = 0  # Reset minor
        current_version[2] = 0  # Reset patch
    new_version_str = ".".join(map(str, current_version))
    return new_version_str


def update_version_in_file(file_path: str, new_version: str, dry_run: bool = False):
    """Updates the version in a single pyproject.toml file."""
    try:
        pyproject_content = Path(file_path).read_text()
        doc = tomlkit.parse(pyproject_content)

        if "project" not in doc or "version" not in doc["project"]:
            print(
                f"Warning: 'project' or 'version' key not found in {file_path}. Skipping."
            )
            return

        if dry_run:
            print(
                f"Would update version in {file_path} from {doc['project']['version']} to {new_version}"
            )
        else:
            doc["project"]["version"] = new_version
            with open(file_path, "w") as f:
                tomlkit.dump(doc, f)
            print(f"Updated version in {file_path} to {new_version}")

    except FileNotFoundError:
        msg = f"Error: File not found: {file_path}"
        raise Error(msg)
    except (TOMLKitError, KeyError) as e:
        msg = f"Error parsing {file_path}: {e}"
        raise Error(msg)
    except Exception as e:
        msg = f"An unexpected error occurred while processing {file_path}: {e}"
        raise Error(msg)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bump the project version.")
    parser.add_argument(
        "bump_type",
        choices=["patch", "minor", "major"],
        help="The type of version bump (patch, minor, or major)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run without modifying files",
    )
    args = parser.parse_args()

    if args.bump_type not in ("patch", "minor", "major"):
        print("bump_type must be 'patch', 'minor', or 'major'")
        sys.exit(1)

    try:
        bump_version(args.bump_type, args.dry_run)
    except Error as e:
        print(str(e))
        sys.exit(1)
