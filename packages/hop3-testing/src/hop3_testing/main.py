# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Hop3 test runner - CLI for deployment testing."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import os
import sys
import warnings
from pathlib import Path

# Suppress cryptography deprecation warnings from paramiko
warnings.filterwarnings("ignore", category=DeprecationWarning, module="paramiko")
warnings.filterwarnings("ignore", message=".*TripleDES.*", category=DeprecationWarning)

from .apps import AppSourceCatalog, DeploymentSession
from .apps.catalog import AppSource
from .targets import DockerTarget, RemoteTarget

EPILOG = """Examples:

  # Test all apps
  hop-test --target docker

  # Test specific app by name
  hop-test --target docker 010-flask-pip-wsgi

  # Test specific app by path
  hop-test --target docker apps/test-apps/010-flask-pip-wsgi

  # Test multiple apps
  hop-test --target docker 010-flask-pip-wsgi 020-nodejs-express

  # Test using shell glob patterns (shell expands the glob)
  hop-test --target docker apps/test-apps/01*
  hop-test --target docker apps/test-apps/0[12]*

  # Mix names and paths
  hop-test --target docker 010-flask-pip-wsgi apps/test-apps/020-nodejs-express

  # Test specific category
  hop-test --target docker --category python-simple

  # Test against remote server
  hop-test --target remote --host myserver.com --ssh-key ~/.ssh/id_rsa

  # Run with pytest instead
  pytest packages/hop3-testing/tests/ -v --target docker
"""


def main() -> None:
    """Main entry point for the hop-test CLI."""
    parser = argparse.ArgumentParser(
        description="Run Hop3 deployment tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EPILOG,
    )

    # Target configuration
    target_group = parser.add_argument_group("Target configuration")
    target_group.add_argument(
        "--target",
        choices=["docker", "remote"],
        default="docker",
        help="Deployment target type (default: docker)",
    )
    target_group.add_argument(
        "--host",
        help="Remote target hostname (for remote target)",
    )
    target_group.add_argument(
        "--port",
        type=int,
        default=22,
        help="Remote target SSH port (default: 22)",
    )
    target_group.add_argument(
        "--user",
        default="hop3",
        help="Remote target SSH user (default: hop3)",
    )
    target_group.add_argument(
        "--ssh-key",
        help="Remote target SSH key path",
    )

    # App selection
    app_group = parser.add_argument_group("Application selection")
    app_group.add_argument(
        "apps",
        nargs="*",
        help="App name(s) or path(s) to test (shell glob patterns supported)",
    )
    app_group.add_argument(
        "--apps-dir",
        type=Path,
        help="Path to test apps directory (default: auto-detect)",
    )
    app_group.add_argument(
        "--category",
        help="Test apps in specific category (e.g., python-simple, nodejs)",
    )

    # Test configuration
    test_group = parser.add_argument_group("Test configuration")
    test_group.add_argument(
        "--keep",
        action="store_true",
        help="Keep apps deployed after testing",
    )
    test_group.add_argument(
        "--keep-target",
        action="store_true",
        help="Keep target running after tests (Docker only)",
    )
    test_group.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first failure",
    )
    test_group.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )
    test_group.add_argument(
        "--debug",
        action="store_true",
        help="Debug mode (show nginx configs, logs, etc.)",
    )

    # Docker-specific options
    docker_group = parser.add_argument_group("Docker options")
    docker_group.add_argument(
        "--use-cache",
        action="store_true",
        help="Skip build entirely if image exists (fastest, but may use stale image)",
    )
    docker_group.add_argument(
        "--no-rebuild",
        action="store_true",
        help="Alias for --use-cache",
    )
    docker_group.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Force full rebuild without using Docker layer cache (slowest)",
    )

    args = parser.parse_args()

    # Create target
    target = create_target(args)

    # Get apps to test
    catalog = AppSourceCatalog(apps_dir=args.apps_dir)
    apps = get_apps_to_test(catalog, args)

    if not apps:
        print("❌ No apps found to test")
        sys.exit(1)

    print(f"\nFound {len(apps)} app(s) to test")
    for app in apps:
        print(f"  - {app.name} ({app.category})")

    # Start target
    print("\nStarting deployment target...")
    try:
        target.start()
    except Exception as e:
        print(f"❌ Failed to start target: {e}")
        sys.exit(1)

    # Run tests
    try:
        results = run_tests(apps, target, args)
        print_results(results)

        # Exit with appropriate status
        failed = [name for name, success in results if not success]
        sys.exit(1 if failed else 0)

    finally:
        # Cleanup
        if not args.keep_target:
            print("\nStopping target...")
            target.stop()


def create_target(args) -> DockerTarget | RemoteTarget:
    """Create deployment target from arguments.

    Args:
        args: Parsed command line arguments

    Returns:
        DeploymentTarget instance
    """
    if args.target == "remote":
        # Get config from args or environment
        host = args.host or os.getenv("HOP3_TEST_HOST")
        if not host:
            print("❌ Remote target requires --host or HOP3_TEST_HOST")
            sys.exit(1)

        config = {
            "host": host,
            "port": args.port,
            "user": args.user,
            "ssh_key": args.ssh_key or os.getenv("HOP3_TEST_SSH_KEY"),
        }
        return RemoteTarget(config)

    # Docker target (default)
    use_cache = args.use_cache or args.no_rebuild
    force_rebuild = args.force_rebuild if hasattr(args, "force_rebuild") else False
    config = {
        "image_tag": "hop3-e2e:test",
        "rebuild": not use_cache,  # Rebuild by default unless --use-cache
        "use_cache": use_cache,
        "force_rebuild": force_rebuild,
    }
    return DockerTarget(config)


def _create_test_app_from_path(app_path: Path) -> AppSource:
    """Create a TestApp instance from a directory path."""
    app_name = app_path.name
    category = "other"

    # Read description from README if available
    description = ""
    readme_path = app_path / "README.md"
    if readme_path.exists():
        with readme_path.open() as f:
            first_line = f.readline().strip()
            if first_line.startswith("#"):
                description = first_line.lstrip("#").strip()

    return AppSource(
        name=app_name,
        path=app_path,
        category=category,
        description=description,
    )


def _is_path_spec(spec: str) -> bool:
    """Check if spec looks like a path (contains path separators or exists)."""
    return "/" in spec or "\\" in spec or Path(spec).exists()


def get_apps_to_test(catalog: AppSourceCatalog, args) -> list:
    """Get list of apps to test based on arguments.

    Args:
        catalog: Test app catalog
        args: Parsed command line arguments

    Returns:
        List of TestApp instances
    """
    if args.apps:
        apps = []
        seen_paths = set()

        for app_spec in args.apps:
            if _is_path_spec(app_spec):
                # Handle path-based spec
                app_path = Path(app_spec).resolve()

                if not app_path.is_dir():
                    print(f"⚠️  Not a directory: {app_spec}")
                    continue

                if app_path in seen_paths:
                    continue

                seen_paths.add(app_path)
                apps.append(_create_test_app_from_path(app_path))
            else:
                # Handle catalog name lookup
                app = catalog.get(app_spec)
                if not app:
                    print(f"⚠️  App not found in catalog: {app_spec}")
                    continue

                if app.path not in seen_paths:
                    seen_paths.add(app.path)
                    apps.append(app)

        return apps

    if args.category:
        return list(catalog.filter(category=args.category))

    return list(catalog)


def run_tests(apps, target, args) -> list[tuple[str, bool]]:
    """Run tests for all apps.

    Args:
        apps: List of TestApp instances
        target: Deployment target
        args: Parsed command line arguments

    Returns:
        List of (app_name, success) tuples
    """
    results = []

    for app in apps:
        print(f"\n{'=' * 70}")
        print(f"Testing: {app.name}")
        print(f"Category: {app.category}")
        if app.description:
            print(f"Description: {app.description}")
        print(f"{'=' * 70}\n")

        # Create deployment session with config
        session_config = {
            "verbose": args.verbose,
            "debug": args.debug,
        }
        session = DeploymentSession(app, target, config=session_config)

        # Run test
        try:
            cleanup = not args.keep
            success = session.run_full_test(cleanup=cleanup)
            results.append((app.name, success))

            if success:
                print(f"\n✓ {app.name} PASSED")
            else:
                print(f"\n❌ {app.name} FAILED")

                if args.fail_fast:
                    print("\nFail fast enabled, stopping tests")
                    break

        except KeyboardInterrupt:
            print("\n\nTests interrupted by user")
            session.cleanup()
            break
        except Exception as e:
            print(f"\n❌ {app.name} FAILED with exception: {e}")
            results.append((app.name, False))

            if args.fail_fast:
                print("\nFail fast enabled, stopping tests")
                break

    return results


def print_results(results: list[tuple[str, bool]]) -> None:
    """Print test results summary.

    Args:
        results: List of (app_name, success) tuples
    """
    print("\n" + "=" * 70)
    print("TEST RESULTS")
    print("=" * 70)

    passed = [name for name, success in results if success]
    failed = [name for name, success in results if not success]

    for app_name, success in results:
        status = "✓ PASS" if success else "❌ FAIL"
        print(f"{status}: {app_name}")

    print("\n" + "=" * 70)
    print(f"Total: {len(results)} | Passed: {len(passed)} | Failed: {len(failed)}")
    print("=" * 70)


if __name__ == "__main__":
    main()
