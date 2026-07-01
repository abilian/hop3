# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""CLI argument parsing for server installer."""

from __future__ import annotations

import argparse

from hop3_installer.constants import DEFAULT_BRANCH_PRODUCTION

from .config import ServerInstallerConfig, parse_features

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
  sudo python3 install-server.py                  Install (PyPI, PostgreSQL only)
  sudo python3 install-server.py --from git       Install from git (main branch)
  sudo python3 install-server.py --from local --path /src   Install from a dir
  sudo python3 install-server.py --with docker    Install with PostgreSQL + Docker
  sudo python3 install-server.py --with all       Install all optional features
  sudo python3 install-server.py --domain hop3.example.com
                                                  Install with Let's Encrypt cert

Optional Features (--with):
  docker      Docker container runtime
  mysql       MySQL database
  nix         Nix package manager (multi-user daemon mode)
  redis       Redis cache/store
  rust        Rust toolchain (rustup)
  s3          S3-compatible object storage (MinIO)
  all         Install all optional features
  (PostgreSQL is always installed and is not a feature. Unknown values error.)
""",
    )

    parser.add_argument(
        "--from",
        dest="from_source",
        choices=["pypi", "git", "local"],
        default=None,
        help="Install source: pypi | git | local (preferred over --git/--path)",
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
        help="Install from git repository (deprecated: use --from git)",
    )
    parser.add_argument(
        "--branch",
        metavar="BRANCH",
        default=env_config.branch,
        help=f"Git branch to install from (default: {DEFAULT_BRANCH_PRODUCTION})",
    )
    parser.add_argument(
        "--path",
        "--local-path",
        dest="local_path",
        metavar="PATH",
        default=env_config.local_path,
        help="Local directory to install from (use with --from local)",
    )
    parser.add_argument(
        "--pre",
        action="store_true",
        default=env_config.pre_release,
        help="Allow pre-release versions when installing from PyPI",
    )
    # `--clean` is the canonical spelling for "start fresh / reinstall over an
    # existing install" (ADR 052 D6); `--force` stays as an alias. `--force` is
    # reserved elsewhere for the client's guard-bypass, so it is not that here.
    parser.add_argument(
        "--clean",
        "--force",
        dest="force",
        action="store_true",
        default=env_config.force,
        help="Clean reinstall over an existing install (recreates the venv)",
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
        help="Comma-separated features: docker,mysql,redis,nix,s3,rust (or 'all')",
    )
    parser.add_argument(
        "--skip-acme",
        action="store_true",
        default=env_config.skip_acme,
        help="Skip ACME/Let's Encrypt setup",
    )
    parser.add_argument(
        "--skip-package-install",
        action="store_true",
        default=env_config.skip_package_install,
        help="Skip the hop3-server package install step. "
        "Use when the package was installed separately (e.g. by hop3-deploy --local).",
    )
    parser.add_argument(
        "--domain",
        metavar="DOMAIN",
        default=env_config.domain,
        help="Domain name for Let's Encrypt certificate",
    )
    parser.add_argument(
        "--acme-email",
        metavar="EMAIL",
        default=env_config.acme_email,
        help="Email address for Let's Encrypt registration (required for ACME)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=env_config.verbose,
        help="Show verbose output",
    )

    return parser


def config_from_args(args: argparse.Namespace) -> ServerInstallerConfig:
    """Create ServerInstallerConfig from parsed arguments.

    ``--from {pypi,git,local}`` is the canonical source selector (ADR 052 D3);
    ``--git``/``--path`` still work. ``--from local`` requires ``--path``.
    """
    features = parse_features(args.with_features)
    if args.from_source == "local" and not args.local_path:
        msg = "--from local requires --path <dir> (a local directory to install from)"
        raise ValueError(msg)
    use_git = args.git or args.from_source == "git"
    return ServerInstallerConfig(
        version=args.version,
        use_git=use_git,
        branch=args.branch,
        local_path=args.local_path,
        pre_release=args.pre,
        force=args.force,
        skip_deps=args.skip_deps,
        skip_nginx=args.skip_nginx,
        skip_postgres=args.skip_postgres,
        skip_acme=args.skip_acme,
        skip_package_install=args.skip_package_install,
        domain=args.domain,
        acme_email=args.acme_email,
        verbose=args.verbose,
        features=features,
    )
