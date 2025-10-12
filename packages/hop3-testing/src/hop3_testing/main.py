# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Hop3 test runner - CLI for deployment testing."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .apps import DeploymentSession, TestAppCatalog
from .targets import DockerTarget, RemoteTarget


def main() -> None:
    """Main entry point for the hop-test CLI."""
    parser = argparse.ArgumentParser(
        description="Run Hop3 deployment tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test all apps using Docker
  hop-test --target docker

  # Test specific app
  hop-test --target docker --app 010-flask-pip-wsgi

  # Test against remote server
  hop-test --target remote --host myserver.com --ssh-key ~/.ssh/id_rsa

  # Test specific category
  hop-test --target docker --category python-simple

  # Run with pytest instead
  pytest packages/hop3-testing/tests/ -v --target docker
        """,
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
        "--apps-dir",
        type=Path,
        help="Path to test apps directory (default: auto-detect)",
    )
    app_group.add_argument(
        "--app",
        help="Test specific app by name",
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
        help="Use cached Docker image instead of rebuilding (faster but may use stale code)",
    )
    docker_group.add_argument(
        "--no-rebuild",
        action="store_true",
        help="Alias for --use-cache",
    )

    args = parser.parse_args()

    # Create target
    target = create_target(args)

    # Get apps to test
    catalog = TestAppCatalog(apps_dir=args.apps_dir)
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
    config = {
        "image_tag": "hop3-e2e:test",
        "rebuild": not use_cache,  # Rebuild by default unless --use-cache
        "use_cache": use_cache,
    }
    return DockerTarget(config)


def get_apps_to_test(catalog: TestAppCatalog, args) -> list:
    """Get list of apps to test based on arguments.

    Args:
        catalog: Test app catalog
        args: Parsed command line arguments

    Returns:
        List of TestApp instances
    """
    if args.app:
        app = catalog.get(args.app)
        return [app] if app else []

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
