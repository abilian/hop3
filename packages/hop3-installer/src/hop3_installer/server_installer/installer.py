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
    ServiceStartError,
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
from .config import ServerInstallerConfig
from .deps import install_system_deps
from .deps_common import (
    install_catalogue_baseline,
    install_elixir,
    install_leiningen,
    install_node_global_packages,
    install_rust_toolchain,
)
from .mysql import setup_mysql
from .nginx import setup_nginx
from .nix import install_nix
from .postgres import setup_postgres
from .python import (
    create_virtual_environment,
    install_package,
    run_hop3_setup,
    setup_ssh_keys,
)
from .rootd import setup_rootd
from .s3 import fix_s3_env_ownership
from .services import setup_systemd
from .ssl import setup_ssl_selfsigned
from .user import create_user_and_group
from .verify import print_final_message, verify_installation, write_server_config

# =============================================================================
# Main
# =============================================================================


def _install_optional_toolchains(config: ServerInstallerConfig) -> None:
    """Install optional toolchains that need hop3 user to exist.

    By default these are non-critical — failures are warnings.
    `--with=rust` promotes the Rust install to critical (raises).

    Args:
        config: Installation configuration.
    """
    # Install Rust toolchain. `--with=rust` makes it a hard requirement
    # (unblocks vaultwarden-native and other Rust-from-source apps).
    try:
        install_rust_toolchain(required=config.with_rust)
    except CommandError as e:
        if config.with_rust:
            raise
        print_warning(f"Rust toolchain installation failed: {e.stderr[:100]}")

    # Install Node.js global packages (pnpm, nodeenv)
    try:
        install_node_global_packages()
    except CommandError as e:
        print_warning(f"Node global packages installation failed: {e.stderr[:100]}")

    # Install Leiningen (Clojure build tool)
    try:
        install_leiningen()
    except CommandError as e:
        print_warning(f"Leiningen installation failed: {e.stderr[:100]}")

    # Install a modern Elixir (Phoenix needs >= 1.15; the distro ships 1.14)
    try:
        install_elixir()
    except CommandError as e:
        print_warning(f"Elixir installation failed: {e.stderr[:100]}")

    # Install Nix package manager (single-user mode needs hop3 user)
    if config.with_nix:
        try:
            install_nix()
        except Exception as e:
            print_warning(f"Nix installation failed: {e}")


def _install_package_step(config: ServerInstallerConfig) -> bool:
    """Step 4: install the hop3-server Python package.

    Honors ``--skip-package-install`` so callers that installed the
    package separately (e.g. ``hop3-deploy --local``) can re-run the
    installer for other steps without clobbering their package install.
    """
    print_step(4, TOTAL_STEPS, "Installing hop3-server...")
    if config.skip_package_install:
        print_info("Skipping package install (--skip-package-install)")
        return True
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
    return True


def _run_critical_steps(distro: str, config: ServerInstallerConfig) -> bool:
    """Run critical installation steps that must succeed.

    Args:
        distro: Detected distribution name.
        config: Installation configuration.

    Returns:
        True if all critical steps succeeded, False otherwise.
    """
    # Step 1: System dependencies, then the catalogue-derived baseline (from
    # apps/*/hop3.toml [build].packages + [run].packages). The baseline stacks
    # on the static base packages; it's idempotent and safe to rerun.
    # `detect_distro()` returns "debian" / "fedora" / "arch" / "unknown" — the
    # baseline table keys match. Both share one failure path: a broken baseline
    # (e.g. a package conflict) leaves native-profile apps unbuildable, so it
    # aborts loudly rather than letting apps fail confusingly downstream.
    print_step(1, TOTAL_STEPS, "Installing system dependencies...")
    try:
        install_system_deps(distro, config)
        if distro in {"debian", "fedora"}:
            install_catalogue_baseline(distro)
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

    # Fix-up files that step 1 wrote before the hop3 group existed.
    # This is a no-op if the relevant features weren't enabled.
    fix_s3_env_ownership()

    # Install optional toolchains (needs hop3 user to exist)
    print_info("Installing optional toolchains...")
    _install_optional_toolchains(config)

    # Step 3: Virtual environment
    # Idempotent: keeps an existing venv unless --force is set. Critical
    # for re-runs (e.g. feature installs), where wiping the venv would
    # silently destroy the package install done in a prior step.
    print_step(3, TOTAL_STEPS, "Creating virtual environment...")
    try:
        create_virtual_environment(force=config.force)
    except CommandError as e:
        print_error(f"Failed to create venv: {e.stderr}")
        return False

    # Step 4: Install package
    if not _install_package_step(config):
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
        secret_key = setup_systemd(config)
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

    # Step 9b: hop3-rootd (privileged-operations daemon, ADR 041). The deploy
    # path depends on it for nginx reloads, so on systemd hosts a failure is
    # fatal — we refuse to finish an install that would leave deploys unable
    # to apply proxy changes. On non-systemd hosts setup_rootd() does the host
    # prep and returns without starting anything (the process manager owns
    # activation), so there is nothing to fail here.
    try:
        setup_rootd()
    except (CommandError, ServiceStartError) as e:
        print_error(f"hop3-rootd setup failed: {e}")
        print_info("hop3-rootd is required for deployments (nginx reloads).")
        raise

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

    # parse_features (via create_parser's env defaults and config_from_args)
    # rejects an unknown --with value loudly; surface it as a clean error, not a
    # traceback.
    try:
        parser = create_parser()
        args = parser.parse_args()
        config = config_from_args(args)
    except ValueError as e:
        print_error(str(e))
        return 1

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
