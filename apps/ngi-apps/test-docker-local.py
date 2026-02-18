#!/usr/bin/env python3
"""Test Docker builds for NGI apps locally."""

import subprocess
import sys
from pathlib import Path


def test_app(app_path: str, base_dir: Path) -> bool:
    """Build a Docker app and return True if successful."""
    # Handle both "docker/app" and "docker-based/app" formats
    if app_path.startswith("docker/"):
        app_name = app_path[7:]  # Remove "docker/" prefix
        full_path = base_dir / "docker-based" / app_name
    elif app_path.startswith("docker-based/"):
        full_path = base_dir / app_path
    else:
        full_path = base_dir / "docker-based" / app_path

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
        print("Usage: test-docker-local.py <app1> [app2] ...")
        print("Example: test-docker-local.py docker/umami docker/ghost")
        sys.exit(1)

    base_dir = Path(__file__).parent.resolve()
    apps = sys.argv[1:]

    successes = 0
    failures = 0

    for app in apps:
        if test_app(app, base_dir):
            successes += 1
        else:
            failures += 1

    print()
    print(f"Results: {successes} success, {failures} failure")
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
