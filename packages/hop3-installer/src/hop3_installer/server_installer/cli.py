# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""CLI argument parsing for server installer."""

from __future__ import annotations

import argparse

from .config import DEFAULT_BRANCH, ServerInstallerConfig, parse_features

TOTAL_STEPS = 11


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    env_config = ServerInstallerConfig.from_env()

    parser = argparse.ArgumentParser(
        prog="install-server.py",
        description="Install the Hop3 Server. Must be run as root.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  sudo python3 install-server.py                  Install with PostgreSQL only
  sudo python3 install-server.py --with docker    Install with PostgreSQL + Docker
  sudo python3 install-server.py --with all       Install all optional features
  sudo python3 install-server.py --domain hop3.example.com
                                                  Install with Let's Encrypt cert

Optional Features (--with):
  docker      Docker container runtime
  mysql       MySQL database
  redis       Redis cache/store
  all         Install all optional features
""",
    )

    parser.add_argument(
        "--version",
        metavar="VERSION",
        default=env_config.version,
        help="Install a specific version (e.g., 0.4.0)",
    )
    parser.add_argument(
        "--git",
        action="store_true",
        default=env_config.use_git,
        help="Install from git repository",
    )
    parser.add_argument(
        "--branch",
        metavar="BRANCH",
        default=env_config.branch,
        help=f"Git branch to install from (default: {DEFAULT_BRANCH})",
    )
    parser.add_argument(
        "--local-path",
        metavar="PATH",
        default=env_config.local_path,
        help="Install from a local directory",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=env_config.force,
        help="Force reinstall",
    )
    parser.add_argument(
        "--skip-deps",
        action="store_true",
        default=env_config.skip_deps,
        help="Skip system dependency installation",
    )
    parser.add_argument(
        "--skip-nginx",
        action="store_true",
        default=env_config.skip_nginx,
        help="Skip nginx setup",
    )
    parser.add_argument(
        "--skip-postgres",
        action="store_true",
        default=env_config.skip_postgres,
        help="Skip PostgreSQL setup",
    )
    parser.add_argument(
        "--with",
        dest="with_features",
        metavar="FEATURES",
        default=",".join(env_config.features) if env_config.features else "",
        help="Comma-separated list of features (mysql,redis,docker,all)",
    )
    parser.add_argument(
        "--skip-acme",
        action="store_true",
        default=env_config.skip_acme,
        help="Skip ACME/Let's Encrypt setup",
    )
    parser.add_argument(
        "--domain",
        metavar="DOMAIN",
        default=env_config.domain,
        help="Domain name for Let's Encrypt certificate",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=env_config.verbose,
        help="Show verbose output",
    )

    return parser


def config_from_args(args: argparse.Namespace) -> ServerInstallerConfig:
    """Create ServerInstallerConfig from parsed arguments."""
    features = parse_features(args.with_features)
    return ServerInstallerConfig(
        version=args.version,
        use_git=args.git,
        branch=args.branch,
        local_path=args.local_path,
        force=args.force,
        skip_deps=args.skip_deps,
        skip_nginx=args.skip_nginx,
        skip_postgres=args.skip_postgres,
        skip_acme=args.skip_acme,
        domain=args.domain,
        verbose=args.verbose,
        features=features,
    )
