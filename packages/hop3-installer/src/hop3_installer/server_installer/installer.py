# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Hop3 Server Installer - Main orchestration.

A single-file installer for the Hop3 Server.
Uses only Python standard library for maximum portability.
Must be run as root.

Usage:
    curl -LsSf https://hop3.cloud/install-server.py | sudo python3 -
    curl -LsSf https://hop3.cloud/install-server.py | sudo python3 - --git
    sudo python3 install-server.py --help
"""

from __future__ import annotations

import os
import sys

from hop3_installer.common import (
    Colors,
    CommandError,
    check_python_version,
    detect_distro,
    print_detail,
    print_error,
    print_header,
    print_info,
    print_step,
    print_warning,
)

from .acme import setup_acme
from .cli import TOTAL_STEPS, config_from_args, create_parser
from .config import ServerInstallerConfig  # noqa: TC001
from .deps import install_system_deps
from .deps_common import install_rust_toolchain
from .mysql import setup_mysql
from .nginx import setup_nginx
from .postgres import setup_postgres
from .python import (
    create_virtual_environment,
    install_package,
    run_hop3_setup,
    setup_ssh_keys,
)
from .services import setup_systemd
from .ssl import setup_ssl_selfsigned
from .user import create_user_and_group
from .verify import print_final_message, verify_installation, write_server_config

# =============================================================================
# Main
# =============================================================================


def _run_critical_steps(distro: str, config: ServerInstallerConfig) -> bool:
    """Run critical installation steps that must succeed.

    Args:
        distro: Detected distribution name.
        config: Installation configuration.

    Returns:
        True if all critical steps succeeded, False otherwise.
    """
    # Step 1: System dependencies
    print_step(1, TOTAL_STEPS, "Installing system dependencies...")
    try:
        install_system_deps(distro, config)
    except CommandError as e:
        print_error(f"Failed to install dependencies: {e.stderr[:200]}")
        return False

    # Step 2: Create user
    print_step(2, TOTAL_STEPS, "Creating hop3 user and group...")
    try:
        create_user_and_group()
    except CommandError as e:
        print_error(f"Failed to create user: {e.stderr}")
        return False

    # Install Rust toolchain (needs hop3 user to exist)
    try:
        install_rust_toolchain()
    except CommandError as e:
        print_warning(f"Rust toolchain installation failed: {e.stderr[:100]}")

    # Step 3: Virtual environment
    print_step(3, TOTAL_STEPS, "Creating virtual environment...")
    try:
        create_virtual_environment()
    except CommandError as e:
        print_error(f"Failed to create venv: {e.stderr}")
        return False

    # Step 4: Install package
    print_step(4, TOTAL_STEPS, "Installing hop3-server...")
    try:
        install_package(config)
    except CommandError as e:
        print_error("Failed to install hop3-server")
        if e.stdout:
            print_detail("--- stdout ---")
            for line in e.stdout.strip().split("\n")[-20:]:
                print_detail(line)
        if e.stderr:
            print_detail("--- stderr ---")
            for line in e.stderr.strip().split("\n")[-20:]:
                print_detail(line)
        return False

    # Step 5: Run setup
    print_step(5, TOTAL_STEPS, "Running initial setup...")
    try:
        run_hop3_setup()
    except CommandError as e:
        print_error(f"Setup failed: {e.stderr[:200]}")
        return False

    return True


def _run_service_setup_steps(
    distro: str, config: ServerInstallerConfig
) -> tuple[str | None, str | None, str | None]:
    """Run service configuration steps (non-critical).

    Args:
        distro: Detected distribution name.
        config: Installation configuration.

    Returns:
        Tuple of (secret_key, pg_password, mysql_password).
    """
    # Step 6: SSH keys
    print_step(6, TOTAL_STEPS, "Configuring SSH keys...")
    setup_ssh_keys()

    # Step 7: Systemd
    print_step(7, TOTAL_STEPS, "Setting up systemd services...")
    secret_key = None
    try:
        secret_key = setup_systemd()
    except CommandError as e:
        print_warning(f"Systemd setup issue: {e.stderr[:100]}")

    # Step 8: SSL certificates
    print_step(8, TOTAL_STEPS, "Setting up SSL certificates...")
    try:
        setup_ssl_selfsigned()
    except CommandError as e:
        print_warning(f"SSL setup issue: {e.stderr[:100]}")

    # Step 9: Nginx
    print_step(9, TOTAL_STEPS, "Configuring nginx...")
    try:
        setup_nginx(config)
    except CommandError as e:
        print_warning(f"Nginx setup issue: {e.stderr[:100]}")

    # Step 10: PostgreSQL
    print_step(10, TOTAL_STEPS, "Configuring PostgreSQL...")
    pg_password = None
    try:
        pg_password = setup_postgres(config, distro)
    except CommandError as e:
        print_warning(f"PostgreSQL setup issue: {e.stderr[:100]}")

    # Step 11: MySQL (if requested)
    print_step(11, TOTAL_STEPS, "Configuring MySQL...")
    mysql_password = None
    try:
        mysql_password = setup_mysql(config, distro)
    except CommandError as e:
        print_warning(f"MySQL setup issue: {e.stderr[:100]}")

    return secret_key, pg_password, mysql_password


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    check_python_version()

    parser = create_parser()
    args = parser.parse_args()
    config = config_from_args(args)

    # Header
    print_header("Hop3 Server Installer")

    # Check root
    if os.geteuid() != 0:
        print_error("This installer must be run as root")
        print_detail("Use: sudo python3 install-server.py")
        return 1

    # Detect distro
    distro = detect_distro()
    print_info(f"Detected distribution: {distro}")

    if config.features:
        print_info(f"Optional features: {', '.join(sorted(config.features))}")

    # Run critical steps (steps 1-5)
    if not _run_critical_steps(distro, config):
        return 1

    # Run service setup steps (steps 6-11)
    secret_key, pg_password, mysql_password = _run_service_setup_steps(distro, config)

    # Write server config (including secret key for CLI commands)
    try:
        write_server_config(pg_password, mysql_password, config.domain, secret_key)
    except Exception as e:
        print_warning(f"Config write issue: {e}")

    # ACME setup
    try:
        setup_acme(config)
    except CommandError as e:
        print_warning(f"ACME setup issue: {e.stderr[:100]}")

    # Verify
    print()
    if not verify_installation(config):
        print_error("Installation verification failed!")
        print_info("Please check the errors above and fix the configuration.")
        return 1

    # Success
    print_final_message(config)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nInstallation cancelled.")
        sys.exit(130)
    except Exception as e:
        print(f"\n{Colors.RED}Error:{Colors.RESET} {e}", file=sys.stderr)
        sys.exit(1)
