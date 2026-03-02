#!/usr/bin/env python3
"""Test Docker builds for packaged apps locally.

Usage:
    # Build all Docker apps
    python test-docker-local.py docker-apps/*

    # Build specific app
    python test-docker-local.py docker-apps/wordpress

    # Build without cache
    python test-docker-local.py --no-cache docker-apps/wordpress
"""

import argparse
import subprocess
import sys
from pathlib import Path


def test_app(app_path: str, logs_dir: Path, no_cache: bool) -> bool:
    """Build a Docker app and return True if successful."""
    full_path = Path(app_path).resolve()

    if not full_path.exists():
        print(f"{app_path}: FAILURE (directory not found)")
        return False

    dockerfile = full_path / "Dockerfile"
    if not dockerfile.exists():
        print(f"{app_path}: FAILURE (no Dockerfile)")
        return False

    cmd = ["docker", "build", "."]
    if no_cache:
        cmd.insert(2, "--no-cache")

    result = subprocess.run(
        cmd,
        cwd=full_path,
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        print(f"{app_path}: SUCCESS")
        return True
    else:
        app_name = full_path.name
        log_file = logs_dir / f"{app_name}.log"
        log_file.write_text(result.stdout + result.stderr)
        print(f"{app_path}: FAILURE (see {log_file})")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test Docker builds for NGI apps")
    parser.add_argument("paths", nargs="+", help="Paths to app directories")
    parser.add_argument("--no-cache", action="store_true", help="Build without cache")
    args = parser.parse_args()

    logs_dir = Path(__file__).parent / "logs" / "docker-builds"
    logs_dir.mkdir(parents=True, exist_ok=True)

    successes = 0
    failures = 0

    for app in args.paths:
        if test_app(app, logs_dir, args.no_cache):
            successes += 1
        else:
            failures += 1

    print()
    print(f"Results: {successes} success, {failures} failure")
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
