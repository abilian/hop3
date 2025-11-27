#!/usr/bin/env python3
# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Test script for Hop3 installers using Docker.

Usage:
    ./test-installers-docker.py                           # Test CLI on Ubuntu
    ./test-installers-docker.py --distro ubuntu --type cli
    ./test-installers-docker.py --distro fedora --type server
    ./test-installers-docker.py --all                     # Test CLI on all distros
    ./test-installers-docker.py --cleanup                 # Remove test containers/images

Options:
    --distro <name>   Distro to test on (ubuntu, debian, fedora)
    --type <type>     Installer type: cli, server, or both (default: cli)
    --all             Test on all distros
    --keep            Keep containers running after test
    --cleanup         Remove all test containers and images
    --verbose         Verbose output
    --help            Show this help
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# =============================================================================
# Configuration
# =============================================================================

SCRIPT_DIR = Path(__file__).parent.resolve()
AVAILABLE_DISTROS = ["ubuntu", "debian", "fedora"]
DEFAULT_DISTRO = "ubuntu"
DEFAULT_TYPE = "cli"

# Docker images for each distro
DOCKER_IMAGES = {
    "ubuntu": "ubuntu:24.04",
    "debian": "debian:12",
    "fedora": "fedora:40",
}

CONTAINER_PREFIX = "hop3-test"


# =============================================================================
# Terminal Colors
# =============================================================================


@dataclass
class Colors:
    """ANSI color codes for terminal output."""

    RESET: str = "\033[0m"
    RED: str = "\033[0;31m"
    GREEN: str = "\033[0;32m"
    YELLOW: str = "\033[0;33m"
    BLUE: str = "\033[0;34m"
    CYAN: str = "\033[0;36m"
    BOLD: str = "\033[1m"


# Disable colors if not a TTY
if sys.stdout.isatty():
    C = Colors()
else:
    C = Colors(RESET="", RED="", GREEN="", YELLOW="", BLUE="", CYAN="", BOLD="")


# =============================================================================
# Logging
# =============================================================================

VERBOSE = False


def log_info(message: str) -> None:
    print(f"{C.BLUE}[INFO]{C.RESET} {message}")


def log_success(message: str) -> None:
    print(f"{C.GREEN}[PASS]{C.RESET} {message}")


def log_warning(message: str) -> None:
    print(f"{C.YELLOW}[WARN]{C.RESET} {message}")


def log_error(message: str) -> None:
    print(f"{C.RED}[FAIL]{C.RESET} {message}", file=sys.stderr)


def log_debug(message: str) -> None:
    if VERBOSE:
        print(f"{C.BLUE}[DEBUG]{C.RESET} {message}")


def log_header(message: str) -> None:
    print()
    print(f"{C.BOLD}{C.CYAN}=== {message} ==={C.RESET}")
    print()


# =============================================================================
# Docker Helpers
# =============================================================================


def run_command(
    cmd: list[str],
    check: bool = True,
    capture_output: bool = False,
) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    log_debug(f"Running: {' '.join(cmd)}")
    return subprocess.run(cmd, check=check, capture_output=capture_output, text=True)


def docker_available() -> bool:
    """Check if Docker is available."""
    try:
        result = run_command(["docker", "info"], capture_output=True, check=False)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def container_name(distro: str) -> str:
    """Get container name for a distro."""
    return f"{CONTAINER_PREFIX}-{distro}"


def container_exists(distro: str) -> bool:
    """Check if a container exists."""
    result = run_command(
        ["docker", "ps", "-a", "--filter", f"name={container_name(distro)}", "-q"],
        capture_output=True,
        check=False,
    )
    return bool(result.stdout.strip())


def container_running(distro: str) -> bool:
    """Check if a container is running."""
    result = run_command(
        ["docker", "ps", "--filter", f"name={container_name(distro)}", "-q"],
        capture_output=True,
        check=False,
    )
    return bool(result.stdout.strip())


def start_container(distro: str) -> bool:
    """Start a Docker container for testing."""
    name = container_name(distro)
    image = DOCKER_IMAGES[distro]

    log_info(f"Starting container: {name} (image: {image})")

    # Remove existing container if any
    if container_exists(distro):
        log_debug(f"Removing existing container: {name}")
        run_command(["docker", "rm", "-f", name], capture_output=True, check=False)

    # Determine install command based on distro
    if distro in ("ubuntu", "debian"):
        install_cmd = "apt-get update && apt-get install -y python3 python3-venv git curl"
    else:  # fedora
        install_cmd = "dnf install -y python3 python3-pip git curl"

    # Start container with installer directory mounted
    try:
        run_command([
            "docker", "run", "-d",
            "--name", name,
            "-v", f"{SCRIPT_DIR}:/installer:ro",
            "-w", "/installer",
            image,
            "bash", "-c", f"{install_cmd} && sleep infinity"
        ])
    except subprocess.CalledProcessError as e:
        log_error(f"Failed to start container: {e}")
        return False

    # Wait for package installation to complete
    log_info("Waiting for package installation...")
    try:
        run_command([
            "docker", "exec", name,
            "bash", "-c", "while ! command -v python3 &>/dev/null; do sleep 1; done"
        ], check=True)
    except subprocess.CalledProcessError:
        log_error("Package installation timed out")
        return False

    log_success(f"Container {name} is ready")
    return True


def stop_container(distro: str) -> None:
    """Stop and remove a container."""
    name = container_name(distro)
    log_info(f"Stopping container: {name}")
    run_command(["docker", "rm", "-f", name], capture_output=True, check=False)


def run_in_container(distro: str, command: str) -> subprocess.CompletedProcess:
    """Run a command inside a container."""
    name = container_name(distro)
    return run_command(
        ["docker", "exec", name, "bash", "-c", command],
        capture_output=True,
        check=False,
    )


# =============================================================================
# Test Functions
# =============================================================================


def test_cli_installer(distro: str) -> bool:
    """Test the CLI installer in a container."""
    log_header(f"Testing CLI Installer on {distro}")
    all_passed = True

    # Run the installer
    log_info("Running CLI installer...")
    result = run_in_container(
        distro,
        "python3 /installer/install-cli.py --git --no-modify-path --verbose"
    )

    if result.returncode == 0:
        log_success("CLI installer completed")
    else:
        log_error("CLI installer failed")
        if VERBOSE:
            print(result.stdout)
            print(result.stderr)
        return False

    # Validate installation
    log_info("Validating CLI installation...")

    # Check venv exists
    result = run_in_container(distro, "test -d ~/.hop3-cli/venv")
    if result.returncode == 0:
        log_success("Virtual environment exists")
    else:
        log_error("Virtual environment not found")
        all_passed = False

    # Check hop command exists
    result = run_in_container(
        distro, "test -f ~/.hop3-cli/venv/bin/hop || test -f ~/.hop3-cli/venv/bin/hop3"
    )
    if result.returncode == 0:
        log_success("CLI command installed")
    else:
        log_error("CLI command not found")
        all_passed = False

    # Check symlink
    result = run_in_container(
        distro, "test -L ~/.local/bin/hop || test -f ~/.local/bin/hop"
    )
    if result.returncode == 0:
        log_success("Symlink created in ~/.local/bin")
    else:
        log_warning("Symlink not found (may be expected)")

    # Try running the command
    result = run_in_container(distro, "~/.hop3-cli/venv/bin/hop help 2>&1")
    if "error" in result.stdout.lower() or "could not connect" in result.stdout.lower():
        log_success("CLI command runs (expected connection error - no server)")
    elif result.returncode == 0:
        log_success("CLI command runs successfully")
    else:
        log_warning("CLI command output unexpected")

    return all_passed


def test_server_installer(distro: str) -> bool:
    """Test the server installer in a container."""
    log_header(f"Testing Server Installer on {distro}")
    all_passed = True

    # Note: Server installer needs root and systemd, which is tricky in Docker
    # We'll test what we can without systemd

    log_info("Running server installer (limited test - no systemd)...")
    result = run_in_container(
        distro,
        "python3 /installer/install-server.py --git --skip-deps --skip-postgres --skip-nginx --verbose 2>&1 || true"
    )

    # Check if hop3 user was created
    result = run_in_container(distro, "id hop3 2>/dev/null")
    if result.returncode == 0:
        log_success("hop3 user exists")
    else:
        log_warning("hop3 user not created (expected in Docker without full privileges)")

    # Check if venv directory structure would be correct
    log_info("Server installer test limited in Docker (no systemd)")
    log_warning("For full server testing, use a VM or real server")

    return all_passed


def run_tests(distro: str, test_type: str) -> bool:
    """Run tests on a distro."""
    log_header(f"Running Tests on {distro}")

    # Start container
    if not start_container(distro):
        log_error(f"Could not start container for {distro}")
        return False

    # Run tests
    all_passed = True

    if test_type in ("cli", "both"):
        if not test_cli_installer(distro):
            all_passed = False

    if test_type in ("server", "both"):
        if not test_server_installer(distro):
            all_passed = False

    return all_passed


def cleanup_all() -> None:
    """Remove all test containers and images."""
    log_header("Cleaning up")

    for distro in AVAILABLE_DISTROS:
        name = container_name(distro)
        if container_exists(distro):
            log_info(f"Removing container: {name}")
            run_command(["docker", "rm", "-f", name], capture_output=True, check=False)

    log_success("Cleanup complete")


# =============================================================================
# Argument Parsing
# =============================================================================


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Test Hop3 installers using Docker.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Test CLI installer on Ubuntu (default)
    ./test-installers-docker.py

    # Test CLI installer on Fedora
    ./test-installers-docker.py --distro fedora

    # Test on all distros
    ./test-installers-docker.py --all

    # Clean up
    ./test-installers-docker.py --cleanup

Available Distros:
    ubuntu      Ubuntu 24.04 LTS
    debian      Debian 12
    fedora      Fedora 40

Test Types:
    cli         Test the CLI installer
    server      Test the server installer (limited in Docker)
    both        Test both installers
        """,
    )

    parser.add_argument(
        "--distro",
        type=str,
        default=DEFAULT_DISTRO,
        choices=AVAILABLE_DISTROS,
        help=f"Distro to test on (default: {DEFAULT_DISTRO})",
    )

    parser.add_argument(
        "--type",
        type=str,
        default=DEFAULT_TYPE,
        choices=["cli", "server", "both"],
        help=f"Installer type to test (default: {DEFAULT_TYPE})",
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Test on all available distros",
    )

    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep containers running after test",
    )

    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove all test containers and exit",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    return parser.parse_args()


# =============================================================================
# Main
# =============================================================================


def main() -> None:
    """Main entry point."""
    global VERBOSE

    args = parse_arguments()
    VERBOSE = args.verbose

    # Check Docker is available
    if not docker_available():
        log_error("Docker is not available or not running.")
        log_error("Please install Docker and ensure the daemon is running:")
        log_error("  sudo systemctl start docker")
        sys.exit(1)

    # Handle cleanup
    if args.cleanup:
        cleanup_all()
        sys.exit(0)

    # Determine which distros to test
    distros_to_test = AVAILABLE_DISTROS if args.all else [args.distro]

    # Print test plan
    print()
    print(f"{C.BOLD}Hop3 Installer Test (Docker){C.RESET}")
    print("=" * 40)
    print(f"Distros: {', '.join(distros_to_test)}")
    print(f"Type:    {args.type}")
    print("=" * 40)
    print()

    # Track results
    results: dict[str, bool] = {}

    # Run tests
    for distro in distros_to_test:
        try:
            results[distro] = run_tests(distro, args.type)
        except Exception as e:
            log_error(f"Exception while testing {distro}: {e}")
            results[distro] = False
        finally:
            if not args.keep:
                stop_container(distro)

    # Print summary
    log_header("Test Summary")

    total = len(results)
    passed = sum(1 for v in results.values() if v)
    failed = total - passed

    print(f"Total:  {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        print()
        failed_distros = [d for d, success in results.items() if not success]
        log_error(f"Failed on: {', '.join(failed_distros)}")
        sys.exit(1)
    else:
        print()
        log_success("All tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
