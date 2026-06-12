# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Shared constants for hop3-installer.

This module centralizes all constants used across CLI installer,
server installer, and deployer to ensure consistency and eliminate
duplication (DRY principle).
"""

from __future__ import annotations

from pathlib import Path

# =============================================================================
# Git Repository
# =============================================================================

GIT_REPO = "https://github.com/abilian/hop3.git"


# =============================================================================
# User and Paths
# =============================================================================

HOP3_USER = "hop3"
HOP3_GROUP = "hop3"
HOME_DIR = Path("/home") / HOP3_USER
VENV_DIR = HOME_DIR / "venv"

# Deploy-time provenance manifest. Written by the installer / deployer and
# read by ``hop3 system info`` to report the exact deployed commit/branch.
BUILD_INFO_PATH = HOME_DIR / "build-info.json"
NGINX_DIR = HOME_DIR / "nginx"
HOP3_SSL_DIR = HOME_DIR / "ssl"  # Per-domain SSL certs

# Binary paths (within venv)
HOP3_SERVER_BIN = VENV_DIR / "bin" / "hop3-server"
UWSGI_BIN = VENV_DIR / "bin" / "uwsgi"

# System paths (self-signed certs for initial setup)
SYSTEM_SSL_DIR = Path("/etc/hop3/ssl")
SYSTEM_SSL_CERT = SYSTEM_SSL_DIR / "hop3.crt"
SYSTEM_SSL_KEY = SYSTEM_SSL_DIR / "hop3.key"
SSL_CERT_VALIDITY_DAYS = 365  # 1 year for self-signed certs (matches
# the per-app cert generator at hop3-server's
# platform/certificates.py — see notes/security.md §3.6.3). ACME via
# certbot is the documented production path; a long-validity
# self-signed cert offered no security benefit and made operators
# slower to migrate to ACME.

# ACME paths
ACME_WEBROOT = Path("/var/www/html")
ACME_CHALLENGE_DIR = ACME_WEBROOT / ".well-known" / "acme-challenge"

# Nginx paths
NGINX_SITES_AVAILABLE = Path("/etc/nginx/sites-available")
NGINX_SITES_ENABLED = Path("/etc/nginx/sites-enabled")
NGINX_CONF_D = Path("/etc/nginx/conf.d")


# =============================================================================
# Network
# =============================================================================

HOP3_SERVER_PORT = 8000
HOP3_SERVER_BIND = f"127.0.0.1:{HOP3_SERVER_PORT}"


# =============================================================================
# Default Values
# =============================================================================

DEFAULT_ADMIN_USER = "admin"
DEFAULT_ADMIN_EMAIL = "admin@example.com"
DEFAULT_SSH_USER = "root"

# Branch defaults (different for production vs development)
DEFAULT_BRANCH_PRODUCTION = "main"
DEFAULT_BRANCH_DEVELOPMENT = "devel"


# =============================================================================
# Docker Defaults
# =============================================================================

DOCKER_IMAGE = "ubuntu:24.04"
DOCKER_CONTAINER_NAME = "hop3-dev"


# =============================================================================
# Package Metadata
# =============================================================================

# Server package
SERVER_PACKAGE_NAME = "hop3-server"
SERVER_PACKAGE_SUBDIR = "packages/hop3-server"

# Privileged-operations daemon (ADR 041). Installed into the same venv as
# the server; the deploy path requires it for nginx reloads.
ROOTD_PACKAGE_NAME = "hop3-rootd"
ROOTD_PACKAGE_SUBDIR = "packages/hop3-rootd"
ROOTD_BIN = VENV_DIR / "bin" / "hop3-rootd"

# CLI package
CLI_PACKAGE_NAME = "hop3-cli"
CLI_PACKAGE_SUBDIR = "packages/hop3-cli"

# CLI installation paths
CLI_INSTALL_DIR = Path.home() / ".hop3-cli"
CLI_VENV_DIR = CLI_INSTALL_DIR / "venv"
CLI_DEFAULT_BIN_DIR = Path.home() / ".local" / "bin"
CLI_COMMANDS = ["hop3", "hop"]


# =============================================================================
# Service Names
# =============================================================================

HOP3_SERVICE = "hop3-server"
HOP3_SERVICE_UNIT = f"{HOP3_SERVICE}.service"
UWSGI_SERVICE = "hop3-uwsgi"
UWSGI_SERVICE_UNIT = f"{UWSGI_SERVICE}.service"


# =============================================================================
# Optional Features
# =============================================================================

ALL_FEATURES = {"mysql", "redis", "docker", "nix", "s3", "rust"}


# =============================================================================
# Shell Configuration
# =============================================================================

SHELL_CONFIGS = {
    "bash": Path.home() / ".bashrc",
    "zsh": Path.home() / ".zshrc",
    "fish": Path.home() / ".config" / "fish" / "config.fish",
}
