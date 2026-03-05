#!/usr/bin/env python3
"""Release all Hop3 packages to PyPI.

This script:
1. Checks that all package versions are aligned with the top-level version
2. Builds all packages using uv build
3. Uploads all packages to PyPI using twine
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PACKAGES = [
    "hop3-cli",
    "hop3-installer",
    "hop3-server",
    "hop3-testing",
    "hop3-tui",
]

ROOT_DIR = Path(__file__).parent.parent
PACKAGES_DIR = ROOT_DIR / "packages"
DIST_DIR = ROOT_DIR / "dist"


class ReleaseError(Exception):
    pass


def main():
    args = parse_args()

    try:
        root_version, package_versions = check_and_display_versions()

        if not args.skip_version_check:
            ensure_versions_aligned(root_version, package_versions)

        if not args.skip_build:
            clean_dist()
            build_packages()

        upload_packages(dry_run=args.dry_run)

        print(f"Release {root_version} complete!")

    except ReleaseError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Release all Hop3 packages to PyPI"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build packages but don't upload to PyPI",
    )
    parser.add_argument(
        "--skip-version-check",
        action="store_true",
        help="Skip version alignment check (not recommended)",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip building packages (use existing dist/)",
    )
    return parser.parse_args()


def check_and_display_versions() -> tuple[str, dict[str, str]]:
    """Check versions and display them to the user."""
    print("Checking version alignment...")
    root_version, package_versions = get_all_versions()

    print(f"Root version: {root_version}")
    print("Package versions:")
    for pkg, version in package_versions.items():
        status = "✓" if version == root_version else "✗"
        print(f"  {status} {pkg}: {version}")
    print()

    return root_version, package_versions


def get_all_versions() -> tuple[str, dict[str, str]]:
    """Get root version and all package versions."""
    root_version = get_version()
    package_versions = {pkg: get_version(pkg) for pkg in PACKAGES}
    return root_version, package_versions


def get_version(package: str | None = None) -> str:
    """Get version for root or a specific package."""
    args = ["--short"]
    if package:
        args = ["--package", package] + args
    return run_uv_version(*args)


def run_uv_version(*args: str) -> str:
    """Run uv version with given arguments and return output."""
    cmd = ["uv", "version", *args]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT_DIR)
    if result.returncode != 0:
        raise ReleaseError(f"Command failed: {' '.join(cmd)}\n{result.stderr}")
    return result.stdout.strip()


def ensure_versions_aligned(root_version: str, package_versions: dict[str, str]):
    """Ensure all packages have the same version as root. Exit on mismatch."""
    mismatched = [
        (pkg, version)
        for pkg, version in package_versions.items()
        if version != root_version
    ]

    if mismatched:
        print("ERROR: Version mismatch detected!")
        print(f"Root version: {root_version}")
        print("Mismatched packages:")
        for pkg, version in mismatched:
            print(f"  {pkg}: {version}")
        print()
        print("Run 'python scripts/bump_version.py' to sync versions.")
        sys.exit(1)

    print("All versions aligned!")
    print()


def clean_dist():
    """Remove existing dist directories."""
    print("Cleaning dist directories...")

    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
        print(f"  Removed {DIST_DIR}")

    for pkg in PACKAGES:
        pkg_dist = PACKAGES_DIR / pkg / "dist"
        if pkg_dist.exists():
            shutil.rmtree(pkg_dist)
            print(f"  Removed {pkg_dist}")

    print()


def build_packages():
    """Build all packages using uv build."""
    print("Building packages...")
    DIST_DIR.mkdir(exist_ok=True)

    for pkg in PACKAGES:
        pkg_path = PACKAGES_DIR / pkg
        print(f"  Building {pkg}...")

        result = subprocess.run(
            ["uv", "build", str(pkg_path)],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print(f"ERROR: Failed to build {pkg}")
            print(result.stderr)
            raise ReleaseError(f"Build failed for {pkg}")

    print()
    print("Built packages:")
    for dist_file in get_dist_files():
        print(f"  {dist_file.name}")
    print()


def get_dist_files() -> list[Path]:
    """Get all distributable files (.whl and .tar.gz) from dist directory."""
    files = []
    for pattern in ["*.whl", "*.tar.gz"]:
        files.extend(DIST_DIR.glob(pattern))
    return sorted(files)


def upload_packages(dry_run: bool = False):
    """Upload all packages to PyPI using twine."""
    dist_files = get_dist_files()

    if not dist_files:
        raise ReleaseError("No distribution files found in dist/")

    if dry_run:
        print("Dry run: Would upload packages to PyPI")
        print("Files that would be uploaded:")
        for dist_file in dist_files:
            print(f"  {dist_file.name}")
        return

    print("Uploading packages to PyPI...")

    result = subprocess.run(
        ["twine", "upload", *[str(f) for f in dist_files]],
        cwd=ROOT_DIR,
    )

    if result.returncode != 0:
        raise ReleaseError("Upload failed")

    print()
    print("Successfully uploaded all packages to PyPI!")


if __name__ == "__main__":
    main()
