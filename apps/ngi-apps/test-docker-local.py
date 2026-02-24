#!/usr/bin/env python3
"""Test Docker builds for NGI apps locally."""

import subprocess
import sys
from pathlib import Path


def test_app(app_path: str) -> bool:
    """Build a Docker app and return True if successful."""
    full_path = Path(app_path).resolve()

    if not full_path.exists():
        print(f"{app_path}: FAILURE (directory not found)")
        return False

    dockerfile = full_path / "Dockerfile"
    if not dockerfile.exists():
        print(f"{app_path}: FAILURE (no Dockerfile)")
        return False

    result = subprocess.run(
        ["docker", "build", "."],
        cwd=full_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if result.returncode == 0:
        print(f"{app_path}: SUCCESS")
        return True
    else:
        print(f"{app_path}: FAILURE")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: test-docker-local.py <path1> [path2] ...")
        print("Example: test-docker-local.py docker-based/umami docker-based/ghost")
        sys.exit(1)

    apps = sys.argv[1:]

    successes = 0
    failures = 0

    for app in apps:
        if test_app(app):
            successes += 1
        else:
            failures += 1

    print()
    print(f"Results: {successes} success, {failures} failure")
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
