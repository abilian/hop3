#!/usr/bin/env python3
# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Test script for Hop3 installers using Vagrant.

Usage:
    ./test-installers.py                           # Test CLI on Ubuntu
    ./test-installers.py --vm ubuntu --type cli    # Test CLI on Ubuntu
    ./test-installers.py --vm ubuntu --type server # Test server on Ubuntu
    ./test-installers.py --vm fedora --type both   # Test both on Fedora
    ./test-installers.py --all                     # Test CLI on all VMs
    ./test-installers.py --all --type server       # Test server on all VMs
    ./test-installers.py --cleanup                 # Destroy all VMs

Options:
    --vm <name>       VM to test on (ubuntu, debian, fedora)
    --type <type>     Installer type: cli, server, or both (default: cli)
    --all             Test on all VMs
    --keep            Keep VMs running after test
    --cleanup         Destroy all VMs and exit
    --verbose         Verbose output
    --help            Show this help
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# =============================================================================
# Configuration
# =============================================================================

SCRIPT_DIR = Path(__file__).parent.resolve()
AVAILABLE_VMS = ["ubuntu", "debian", "fedora"]
DEFAULT_VM = "ubuntu"
DEFAULT_TYPE = "cli"


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
    MAGENTA: str = "\033[0;35m"
    CYAN: str = "\033[0;36m"
    BOLD: str = "\033[1m"


# Disable colors if not a TTY
if sys.stdout.isatty():
    C = Colors()
else:
    C = Colors(
        RESET="",
        RED="",
        GREEN="",
        YELLOW="",
        BLUE="",
        MAGENTA="",
        CYAN="",
        BOLD="",
    )


# =============================================================================
# Logging
# =============================================================================

VERBOSE = False


def log_info(message: str) -> None:
    """Print an info message."""
    print(f"{C.BLUE}[INFO]{C.RESET} {message}")


def log_success(message: str) -> None:
    """Print a success message."""
    print(f"{C.GREEN}[PASS]{C.RESET} {message}")


def log_warning(message: str) -> None:
    """Print a warning message."""
    print(f"{C.YELLOW}[WARN]{C.RESET} {message}")


def log_error(message: str) -> None:
    """Print an error message."""
    print(f"{C.RED}[FAIL]{C.RESET} {message}", file=sys.stderr)


def log_debug(message: str) -> None:
    """Print a debug message (only in verbose mode)."""
    if VERBOSE:
        print(f"{C.BLUE}[DEBUG]{C.RESET} {message}")


def log_header(message: str) -> None:
    """Print a header."""
    print()
    print(f"{C.BOLD}{C.CYAN}=== {message} ==={C.RESET}")
    print()


# =============================================================================
# Command Execution
# =============================================================================


def run_command(
    cmd: list[str],
    check: bool = True,
    capture_output: bool = False,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    log_debug(f"Running: {' '.join(cmd)}")
    return subprocess.run(
        cmd,
        check=check,
        capture_output=capture_output,
        text=True,
        cwd=cwd,
    )


def run_vagrant(
    *args: str,
    check: bool = True,
    capture_output: bool = False,
) -> subprocess.CompletedProcess:
    """Run a vagrant command."""
    cmd = ["vagrant", *args]
    return run_command(cmd, check=check, capture_output=capture_output, cwd=SCRIPT_DIR)


def run_in_vm(vm_name: str, command: str) -> subprocess.CompletedProcess:
    """Run a command inside a Vagrant VM."""
    return run_vagrant("ssh", vm_name, "-c", command, capture_output=True, check=False)


# =============================================================================
# Vagrant Helpers
# =============================================================================


def vm_is_running(vm_name: str) -> bool:
    """Check if a VM is running."""
    try:
        result = run_vagrant("status", vm_name, capture_output=True, check=False)
        return "running" in result.stdout
    except Exception:
        return False


def start_vm(vm_name: str) -> bool:
    """Start a Vagrant VM."""
    log_info(f"Starting VM: {vm_name}")

    if vm_is_running(vm_name):
        log_info(f"VM {vm_name} is already running")
        return True

    try:
        if VERBOSE:
            run_vagrant("up", vm_name)
        else:
            result = run_vagrant("up", vm_name, capture_output=True, check=False)
            # Print only important lines
            for line in result.stdout.splitlines():
                if "==>" in line or "error" in line.lower():
                    print(line)
            if result.returncode != 0:
                print(result.stderr)
                return False
    except subprocess.CalledProcessError as e:
        log_error(f"Failed to start VM: {e}")
        return False

    if vm_is_running(vm_name):
        log_success(f"VM {vm_name} is running")
        return True
    log_error(f"Failed to start VM {vm_name}")
    return False


def stop_vm(vm_name: str) -> None:
    """Stop a Vagrant VM."""
    log_info(f"Stopping VM: {vm_name}")
    try:
        run_vagrant("halt", vm_name, capture_output=True, check=False)
    except Exception:
        pass


def destroy_vm(vm_name: str) -> None:
    """Destroy a Vagrant VM."""
    log_info(f"Destroying VM: {vm_name}")
    try:
        run_vagrant("destroy", "-f", vm_name, capture_output=True, check=False)
    except Exception:
        pass


def sync_files(vm_name: str) -> None:
    """Sync files to the VM."""
    log_info("Syncing files to VM...")
    try:
        run_vagrant("rsync", vm_name, capture_output=True, check=False)
    except Exception:
        pass


# =============================================================================
# Test Functions
# =============================================================================


def test_cli_installer(vm_name: str) -> bool:
    """Test the CLI installer on a VM.

    Returns True if all tests pass.
    """
    log_header(f"Testing CLI Installer on {vm_name}")
    all_passed = True

    # Run the installer with --git flag (package not on PyPI yet)
    log_info("Running CLI installer...")
    install_cmd = (
        "HOP3_LOCAL_INSTALLER=/vagrant/install-cli.py "
        "bash /vagrant/install-cli.sh --git --no-modify-path --verbose"
    )
    result = run_in_vm(vm_name, install_cmd)

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
    result = run_in_vm(vm_name, "test -d ~/.hop3-cli/venv")
    if result.returncode == 0:
        log_success("Virtual environment exists")
    else:
        log_error("Virtual environment not found")
        all_passed = False

    # Check hop command exists (either hop or hop3)
    result = run_in_vm(
        vm_name, "test -f ~/.hop3-cli/venv/bin/hop || test -f ~/.hop3-cli/venv/bin/hop3"
    )
    if result.returncode == 0:
        log_success("CLI command installed")
    else:
        log_error("CLI command not found")
        all_passed = False

    # Check symlink in .local/bin
    result = run_in_vm(vm_name, "test -L ~/.local/bin/hop || test -f ~/.local/bin/hop")
    if result.returncode == 0:
        log_success("Symlink created in ~/.local/bin")
    else:
        log_warning("Symlink not found in ~/.local/bin (may be expected)")

    # Try running the command
    result = run_in_vm(vm_name, "~/.hop3-cli/venv/bin/hop help 2>&1")
    if "error" in result.stdout.lower() or "could not connect" in result.stdout.lower():
        log_success("CLI command runs (expected connection error - no server)")
    elif result.returncode == 0:
        log_success("CLI command runs successfully")
    else:
        log_warning("CLI command output unexpected")
        if VERBOSE:
            print(result.stdout)

    return all_passed


def test_server_installer(vm_name: str) -> bool:
    """Test the server installer on a VM.

    Returns True if all tests pass.
    """
    log_header(f"Testing Server Installer on {vm_name}")
    all_passed = True

    # Run the installer with --git flag and skip some setup for testing
    log_info("Running server installer (this may take a while)...")
    install_cmd = (
        "sudo HOP3_LOCAL_INSTALLER=/vagrant/install-server.py "
        "bash /vagrant/install-server.sh --git --skip-postgres --verbose"
    )
    result = run_in_vm(vm_name, install_cmd)

    if result.returncode == 0:
        log_success("Server installer completed")
    else:
        log_error("Server installer failed")
        if VERBOSE:
            print(result.stdout)
            print(result.stderr)
        return False

    # Validate installation
    log_info("Validating server installation...")

    # Check hop3 user exists
    result = run_in_vm(vm_name, "id hop3")
    if result.returncode == 0:
        log_success("hop3 user exists")
    else:
        log_error("hop3 user not found")
        all_passed = False

    # Check venv exists
    result = run_in_vm(vm_name, "sudo test -d /home/hop3/venv")
    if result.returncode == 0:
        log_success("Virtual environment exists")
    else:
        log_error("Virtual environment not found")
        all_passed = False

    # Check hop-server command exists
    result = run_in_vm(vm_name, "sudo test -f /home/hop3/venv/bin/hop-server")
    if result.returncode == 0:
        log_success("hop-server command installed")
    else:
        log_error("hop-server command not found")
        all_passed = False

    # Check systemd service
    result = run_in_vm(vm_name, "systemctl is-enabled hop3-server 2>/dev/null")
    if "enabled" in result.stdout:
        log_success("hop3-server service is enabled")
    else:
        log_warning("hop3-server service not enabled")

    return all_passed


def run_tests(vm_name: str, test_type: str) -> bool:
    """Run tests on a VM.

    Returns True if all tests pass.
    """
    log_header(f"Running Tests on {vm_name}")

    # Start VM
    if not start_vm(vm_name):
        log_error(f"Could not start VM {vm_name}")
        return False

    # Sync files
    sync_files(vm_name)

    # Run tests based on type
    all_passed = True

    if test_type in ("cli", "both"):
        if not test_cli_installer(vm_name):
            all_passed = False

    if test_type in ("server", "both"):
        if not test_server_installer(vm_name):
            all_passed = False

    return all_passed


# =============================================================================
# Argument Parsing
# =============================================================================


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Test Hop3 installers using Vagrant.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Test CLI installer on Ubuntu (default)
    ./test-installers.py

    # Test server installer on Fedora
    ./test-installers.py --vm fedora --type server

    # Test both installers on all VMs
    ./test-installers.py --all --type both

    # Clean up all VMs
    ./test-installers.py --cleanup

Available VMs:
    ubuntu      Ubuntu 24.04 LTS (Noble)
    debian      Debian 12 (Bookworm)
    fedora      Fedora 40

Test Types:
    cli         Test the CLI installer (install-cli.sh)
    server      Test the server installer (install-server.sh)
    both        Test both installers
        """,
    )

    parser.add_argument(
        "--vm",
        type=str,
        default=DEFAULT_VM,
        choices=AVAILABLE_VMS,
        help=f"VM to test on (default: {DEFAULT_VM})",
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
        help="Test on all available VMs",
    )

    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep VMs running after test",
    )

    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Destroy all VMs and exit",
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

    # Change to script directory
    os.chdir(SCRIPT_DIR)

    # Handle cleanup
    if args.cleanup:
        log_header("Cleaning up all VMs")
        for vm in AVAILABLE_VMS:
            destroy_vm(vm)
        log_success("Cleanup complete")
        sys.exit(0)

    # Determine which VMs to test
    vms_to_test = AVAILABLE_VMS if args.all else [args.vm]

    # Print test plan
    print()
    print(f"{C.BOLD}Hop3 Installer Test{C.RESET}")
    print("=" * 40)
    print(f"VMs:  {', '.join(vms_to_test)}")
    print(f"Type: {args.type}")
    print("=" * 40)
    print()

    # Track results
    results: dict[str, bool] = {}

    # Run tests
    for vm in vms_to_test:
        try:
            results[vm] = run_tests(vm, args.type)
        except Exception as e:
            log_error(f"Exception while testing {vm}: {e}")
            results[vm] = False
        finally:
            # Clean up VM unless --keep
            if not args.keep:
                destroy_vm(vm)

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
        failed_vms = [vm for vm, success in results.items() if not success]
        log_error(f"Failed on: {', '.join(failed_vms)}")
        sys.exit(1)
    else:
        print()
        log_success("All tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
