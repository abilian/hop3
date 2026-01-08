# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""CLI for Hop3 deployment."""

from __future__ import annotations

import argparse
import sys

from .config import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_USER,
    DEFAULT_BRANCH,
    DEFAULT_SSH_USER,
    DOCKER_CONTAINER_NAME,
    DOCKER_IMAGE,
    DeployConfig,
)
from .deploy import create_backend, deploy


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        prog="hop3-deploy",
        description="Deploy Hop3 to a server or Docker container",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  HOP3_DEV_HOST      Target server hostname (alternative to --host)
  HOP3_TEST_SERVER   Alias for HOP3_DEV_HOST
  HOP3_SSH_USER      SSH user (default: root)
  HOP3_BRANCH        Git branch (default: devel)
  HOP3_LOCAL         Use local code (1 or true)
  HOP3_CLEAN         Clean before deploy (1 or true)
  HOP3_WITH          Features to install (comma-separated)
  HOP3_DOCKER        Use Docker instead of SSH (1 or true)
  HOP3_QUIET         Quiet mode - minimal output (1 or true)

Examples:
  # Deploy to remote server
  hop3-deploy --host 192.168.1.100

  # Deploy to Docker container
  hop3-deploy --docker

  # Deploy with local code changes
  hop3-deploy --host server.example.com --local

  # Clean install with admin setup
  hop3-deploy --host server.example.com --clean --admin-domain admin.example.com

  # Using environment variables
  export HOP3_DEV_HOST=192.168.1.100
  hop3-deploy --local
""",
    )

    # Target options
    target = parser.add_argument_group("Target")
    target.add_argument(
        "--host",
        "-H",
        help="Target server hostname or IP (or set HOP3_DEV_HOST)",
    )
    target.add_argument(
        "--docker",
        "-d",
        action="store_true",
        help="Deploy to local Docker container instead of SSH",
    )
    target.add_argument(
        "--docker-image",
        default=DOCKER_IMAGE,
        help=f"Docker image to use (default: {DOCKER_IMAGE})",
    )
    target.add_argument(
        "--docker-container",
        default=DOCKER_CONTAINER_NAME,
        help=f"Docker container name (default: {DOCKER_CONTAINER_NAME})",
    )
    target.add_argument(
        "--ssh-user",
        "-u",
        default=DEFAULT_SSH_USER,
        help=f"SSH user (default: {DEFAULT_SSH_USER})",
    )

    # Installation options
    install = parser.add_argument_group("Installation")
    install.add_argument(
        "--branch",
        "-b",
        default=DEFAULT_BRANCH,
        help=f"Git branch to deploy (default: {DEFAULT_BRANCH})",
    )
    install.add_argument(
        "--local",
        "-l",
        action="store_true",
        dest="use_local",
        help="Upload and use local code instead of git",
    )
    install.add_argument(
        "--skip-install",
        action="store_true",
        help="Skip installation (only upload code if --local)",
    )
    install.add_argument(
        "--clean",
        "-c",
        action="store_true",
        help="Clean existing installation before deploying",
    )
    install.add_argument(
        "--with",
        "-w",
        dest="features",
        help="Features to install (comma-separated, e.g., docker,podman)",
    )

    # Admin options
    admin = parser.add_argument_group("Admin Setup")
    admin.add_argument(
        "--admin-domain",
        help="Domain for admin interface (enables admin setup)",
    )
    admin.add_argument(
        "--admin-user",
        default=DEFAULT_ADMIN_USER,
        help=f"Admin username (default: {DEFAULT_ADMIN_USER})",
    )
    admin.add_argument(
        "--admin-email",
        default=DEFAULT_ADMIN_EMAIL,
        help=f"Admin email (default: {DEFAULT_ADMIN_EMAIL})",
    )
    admin.add_argument(
        "--admin-password",
        help="Admin password (auto-generated if not provided)",
    )

    # Output options
    output = parser.add_argument_group("Output")
    output.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )
    output.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Quiet mode - minimal output, capture all output to log file",
    )
    output.add_argument(
        "--log-file",
        metavar="FILE",
        help="Log file for captured output (default: deploy-TIMESTAMP.log)",
    )
    output.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show what would be done without executing",
    )
    output.add_argument(
        "--no-cli-setup",
        action="store_true",
        help="Don't configure local CLI after deployment",
    )

    # Actions
    actions = parser.add_argument_group("Actions")
    actions.add_argument(
        "--status",
        action="store_true",
        help="Show deployment target status and exit",
    )
    actions.add_argument(
        "--teardown",
        action="store_true",
        help="Teardown Docker container and exit",
    )

    return parser


def _apply_target_overrides(config: DeployConfig, args: argparse.Namespace) -> None:
    """Apply target-related CLI overrides to config."""
    if args.host:
        config.host = args.host
    if args.docker:
        config.use_docker = True
    if args.docker_image != DOCKER_IMAGE:
        config.docker_image = args.docker_image
    if args.docker_container != DOCKER_CONTAINER_NAME:
        config.docker_container = args.docker_container
    if args.ssh_user != DEFAULT_SSH_USER:
        config.ssh_user = args.ssh_user


def _apply_install_overrides(config: DeployConfig, args: argparse.Namespace) -> None:
    """Apply installation-related CLI overrides to config."""
    if args.branch != DEFAULT_BRANCH:
        config.branch = args.branch
    if args.use_local:
        config.use_local_code = True
    if args.skip_install:
        config.skip_install = True
    if args.clean:
        config.clean_before = True
    if args.features:
        config.with_features = [f.strip() for f in args.features.split(",")]


def _apply_admin_overrides(config: DeployConfig, args: argparse.Namespace) -> None:
    """Apply admin user CLI overrides to config."""
    if args.admin_domain:
        config.admin_domain = args.admin_domain
    if args.admin_user != DEFAULT_ADMIN_USER:
        config.admin_user = args.admin_user
    if args.admin_email != DEFAULT_ADMIN_EMAIL:
        config.admin_email = args.admin_email
    if args.admin_password:
        config.admin_password = args.admin_password


def _apply_output_overrides(config: DeployConfig, args: argparse.Namespace) -> None:
    """Apply output-related CLI overrides to config."""
    if args.verbose:
        config.verbose = True
    if args.quiet:
        config.quiet = True
    if args.log_file:
        from pathlib import Path

        config.log_file = Path(args.log_file)
    if args.dry_run:
        config.dry_run = True
    if args.no_cli_setup:
        config.no_cli_setup = True


def config_from_args(args: argparse.Namespace) -> DeployConfig:
    """Create DeployConfig from parsed arguments."""
    config = DeployConfig.from_env()

    _apply_target_overrides(config, args)
    _apply_install_overrides(config, args)
    _apply_admin_overrides(config, args)
    _apply_output_overrides(config, args)

    return config


def show_status(config: DeployConfig) -> int:
    """Show status of deployment target."""
    print("Deployment Target Status")
    print("=" * 40)

    backend = create_backend(config)

    if config.use_docker:
        print("Type: Docker")
        print(f"Container: {config.docker_container}")
        print(f"Image: {config.docker_image}")
    else:
        print("Type: SSH")
        print(f"Target: {config.ssh_target}")

    print()
    print("Checking connectivity...")

    if backend.setup():
        print("✓ Target is reachable")

        if backend.is_hop3_installed():
            print("✓ Hop3 is installed")
        else:
            print("✗ Hop3 is not installed")

        print(f"Server URL: {backend.get_server_url()}")
        return 0

    print("✗ Target is not reachable")
    return 1


def do_teardown(config: DeployConfig) -> int:
    """Teardown Docker container."""
    if not config.use_docker:
        print("Teardown only applies to Docker targets")
        return 1

    from .backends.docker import DockerDeployBackend

    backend = DockerDeployBackend(config)
    print(f"Removing container: {config.docker_container}")
    backend.teardown()
    print("✓ Container removed")
    return 0


def _print_deployment_banner(config: DeployConfig) -> None:
    """Print deployment banner showing configuration."""
    if config.quiet:
        target = (
            f"Docker ({config.docker_container})"
            if config.use_docker
            else config.ssh_target
        )
        print(f"Deploying to {target}...")
        return

    print("Hop3 Deployment")
    print("=" * 60)
    if config.use_docker:
        print(f"Target: Docker container ({config.docker_container})")
    else:
        print(f"Target: {config.ssh_target}")
    print(f"Branch: {config.branch}")
    print(f"Local code: {'yes' if config.use_local_code else 'no'}")
    print(f"Clean install: {'yes' if config.clean_before else 'no'}")
    print(f"Features: {', '.join(config.with_features)}")
    if config.admin_domain:
        print(f"Admin domain: {config.admin_domain}")
    print("=" * 60)


def _handle_validation_errors(errors: list[str]) -> int:
    """Print validation errors and return exit code."""
    print("Configuration errors:")
    for error in errors:
        print(f"  • {error}")
    print()
    print("Use --help for usage information")
    return 1


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()
    config = config_from_args(args)

    # Handle special actions
    if args.teardown:
        config.use_docker = True  # Force docker for teardown
        return do_teardown(config)

    if args.status:
        errors = config.validate()
        if errors:
            for error in errors:
                print(f"Error: {error}")
            return 1
        return show_status(config)

    # Validate config
    errors = config.validate()
    if errors:
        return _handle_validation_errors(errors)

    _print_deployment_banner(config)

    if config.dry_run:
        print("\n[Dry run - no changes made]")
        return 0

    # Run deployment
    success = deploy(config)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
