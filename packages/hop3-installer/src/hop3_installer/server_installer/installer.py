# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Hop3 Server Installer - Main orchestration.

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
    InstallStepError,
    ServiceStartError,
    check_python_version,
    detect_distro,
    print_detail,
    print_error,
    print_failure_output,
    print_header,
    print_info,
    print_step,
)
from hop3_installer.deprecation import warn_deprecated_flags

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
from .mailpit import install_mailpit
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
from .services import restart_hop3_server, setup_systemd
from .ssl import setup_ssl_selfsigned
from .user import create_user_and_group
from .verify import print_final_message, verify_installation, write_server_config

# =============================================================================
# Main
# =============================================================================


def _install_optional_toolchains(config: ServerInstallerConfig) -> None:
    """
    Install the toolchains that need the hop3 user to exist.

    Node's package tooling (the pinned pnpm, nodeenv) belongs to every server,
    like Node, and a failure aborts. Rust, Leiningen and Elixir are
    best-effort: an app that needs one fails at its build, saying so, unless
    it was requested by name (`--with rust|clojure|elixir`), which makes a
    failure abort the install. Nix is requested by name or not installed.

    Args:
        config: Installation configuration.
    """
    install_node_global_packages()
    install_rust_toolchain(required=config.with_rust)
    install_leiningen(required=config.with_clojure)
    install_elixir(required=config.with_elixir)

    # Install Nix package manager (single-user mode needs hop3 user). Asked for
    # by name, so a failure aborts the install rather than warn and go on.
    if config.with_nix:
        install_nix()


def _install_package_step(config: ServerInstallerConfig) -> bool:
    """
    Step 4: install the hop3-server Python package.

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
    except OSError as e:
        # The package installed but an executable the platform depends on could
        # not be published (see publish_fetch_helper). A server that simply does
        # not ship it is handled there and is not an error.
        print_error(str(e))
        return False
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
    """
    Steps 1-5. A failing step raises, and `main` prints its whole output: the
    handlers here printed 200 characters of stderr, which for a command that
    reports on stdout was nothing at all ("Failed to install dependencies: ").

    Args:
        distro: Detected distribution name.
        config: Installation configuration.

    Returns:
        False if the package install failed (step 4 reports its own output).
    """
    # Step 1: System dependencies, then the catalogue-derived baseline (from
    # apps/*/hop3.toml [build].packages + [run].packages). The baseline stacks
    # on the static base packages; it's idempotent and safe to rerun.
    # `detect_distro()` returns "debian" / "fedora" / "arch" / "unknown" — the
    # baseline table keys match. Both share one failure path: a broken baseline
    # (e.g. a package conflict) leaves native-profile apps unbuildable, so it
    # aborts loudly rather than letting apps fail confusingly downstream.
    print_step(1, TOTAL_STEPS, "Installing system dependencies...")
    install_system_deps(distro, config)
    if distro in {"debian", "fedora"}:
        install_catalogue_baseline(distro)

    # Step 2: Create user
    print_step(2, TOTAL_STEPS, "Creating hop3 user and group...")
    create_user_and_group()

    # Fix-up files that step 1 wrote before the hop3 group existed.
    # This is a no-op if the relevant features weren't enabled.
    fix_s3_env_ownership()

    # The email catch sink runs as the hop3 user, so it comes after step 2;
    # Postfix itself was pre-staged with the system packages.
    if config.with_email:
        install_mailpit()

    # Install optional toolchains (needs hop3 user to exist)
    print_info("Installing optional toolchains...")
    _install_optional_toolchains(config)

    # Step 3: Virtual environment
    # Idempotent: keeps an existing venv unless --clean is set. Critical
    # for re-runs (e.g. feature installs), where wiping the venv would
    # silently destroy the package install done in a prior step.
    print_step(3, TOTAL_STEPS, "Creating virtual environment...")
    create_virtual_environment(force=config.force)

    # Step 4: Install package
    if not _install_package_step(config):
        return False

    # Step 5: Run setup
    print_step(5, TOTAL_STEPS, "Running initial setup...")
    run_hop3_setup()

    return True


def _run_service_setup_steps(
    distro: str, config: ServerInstallerConfig
) -> tuple[str | None, str | None, str | None]:
    """
    Run the service configuration steps; each raises on failure.

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
    secret_key = setup_systemd(config)

    # Step 8: SSL certificates
    print_step(8, TOTAL_STEPS, "Setting up SSL certificates...")
    setup_ssl_selfsigned()

    # Step 9: Nginx
    print_step(9, TOTAL_STEPS, "Configuring nginx...")
    setup_nginx(config)

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
    pg_password = setup_postgres(config, distro)

    # Step 11: MySQL (if requested)
    print_step(11, TOTAL_STEPS, "Configuring MySQL...")
    mysql_password = setup_mysql(config, distro)

    return secret_key, pg_password, mysql_password


def _configure_server(distro: str, config: ServerInstallerConfig) -> None:
    """
    Steps 6-11, then the config file, ACME and the restart that loads them.

    Raises:
        CommandError, ServiceStartError, OSError, InstallStepError: a step
            failed. The database steps raise rather than return no password,
            so a requested database always arrives here with a verified one.
    """
    secret_key, pg_password, mysql_password = _run_service_setup_steps(distro, config)

    # Server config (including the secret key for CLI commands). Verification
    # keys its database checks on this file existing, so a failed write that
    # carried on also skipped them, and the install reported success.
    write_server_config(
        pg_password,
        mysql_password,
        config.domain,
        secret_key,
        operator_email=config.operator_email or config.acme_email,
    )
    setup_acme(config)

    # hop3-server was started (step 7) BEFORE hop3-server.toml existed, and the
    # config loader caches the file at boot. Restart now that the config is
    # finalized so the running process sees OPERATOR_EMAIL / DB creds / domain —
    # otherwise a fresh install serves a stale config (see restart_hop3_server).
    restart_hop3_server()


def _report_failure(e: Exception) -> None:
    """Print why the install stopped, with the failing command's output."""
    print_error(f"Installation failed: {e}")
    if isinstance(e, CommandError):
        print_failure_output("stderr", e.stderr)
        print_failure_output("stdout", e.stdout)


def main() -> int:
    """
    Main entry point.

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
        warn_deprecated_flags(
            sys.argv[1:],
            {"--git": "--from git", "--local-path": "--path", "--force": "--clean"},
        )
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
    print_info(f"Detected distribution family: {distro}")

    if config.features:
        print_info(f"Optional features: {', '.join(sorted(config.features))}")

    # Steps 1-5, then 6-11 with the config file and ACME. Steps 6-11 raise on
    # failure: they used to be caught one by one and printed as a warning
    # (error output cut to 100 characters), so a failed nginx, SSL or config
    # write ended in an install that reported success.
    try:
        if not _run_critical_steps(distro, config):
            return 1
        _configure_server(distro, config)
    except (CommandError, ServiceStartError, OSError, InstallStepError) as e:
        _report_failure(e)
        return 1

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
