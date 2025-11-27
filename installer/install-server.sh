#!/bin/sh
# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
#
# Hop3 Server Installer Bootstrap Script
#
# This script performs minimal environment validation and downloads
# the Python installer to do the actual work.
#
# Usage:
#   curl -LsSf https://hop3.cloud/install-server.sh | sudo bash
#   curl -LsSf https://hop3.cloud/install-server.sh | sudo bash -s -- --git
#   curl -LsSf https://hop3.cloud/install-server.sh | sudo bash -s -- --version 0.4.0
#
# Environment variables:
#   HOP3_FORCE_REINSTALL  Force reinstall (1 or true)
#   HOP3_VERBOSE          Enable verbose output (1 or true)
#   HOP3_VERSION          Install specific version
#   HOP3_GIT              Install from git (1 or true)
#   HOP3_LOCAL_PACKAGE    Local package directory (for testing)
#   HOP3_SKIP_DEPS        Skip system dependency installation (1 or true)
#   HOP3_SKIP_NGINX       Skip nginx setup (1 or true)
#   HOP3_SKIP_POSTGRES    Skip PostgreSQL setup (1 or true)

# Re-execute with bash if not already running in bash
# This ensures we have access to bash-specific features if needed
if [ -z "$BASH_VERSION" ]; then
    if command -v bash >/dev/null 2>&1; then
        exec bash "$0" "$@"
    fi
fi

set -e

# =============================================================================
# Configuration
# =============================================================================

INSTALLER_URL="${HOP3_INSTALLER_URL:-https://hop3.cloud/install-server.py}"
INSTALLER_PATH="/tmp/hop3-install-server.py"
MIN_PYTHON_VERSION_MAJOR=3
MIN_PYTHON_VERSION_MINOR=10

# For local testing: set HOP3_LOCAL_INSTALLER to the path of install-server.py
LOCAL_INSTALLER="${HOP3_LOCAL_INSTALLER:-}"

# =============================================================================
# Colors
# =============================================================================

if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    BLUE='\033[0;34m'
    BOLD='\033[1m'
    RESET='\033[0m'
else
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    BOLD=''
    RESET=''
fi

# =============================================================================
# Logging Functions
# =============================================================================

log_info() {
    printf "${BLUE}[INFO]${RESET} %s\n" "$1"
}

log_success() {
    printf "${GREEN}[OK]${RESET} %s\n" "$1"
}

log_warning() {
    printf "${YELLOW}[WARN]${RESET} %s\n" "$1"
}

log_error() {
    printf "${RED}[ERROR]${RESET} %s\n" "$1" >&2
}

# =============================================================================
# Help
# =============================================================================

usage() {
    cat <<EOF
Hop3 Server Installer

Usage:
    curl -LsSf https://hop3.cloud/install-server.sh | sudo bash
    curl -LsSf https://hop3.cloud/install-server.sh | sudo bash -s -- [OPTIONS]

Options:
    --force             Force reinstall even if already installed
    --verbose           Enable verbose output
    --version VERSION   Install a specific version (e.g., 0.4.0)
    --git               Install from git (head of main branch)
    --skip-deps         Skip system dependency installation
    --skip-nginx        Skip nginx setup
    --skip-postgres     Skip PostgreSQL setup
    --help              Show this help message

Environment Variables:
    HOP3_FORCE_REINSTALL    Set to '1' or 'true' to force reinstall
    HOP3_VERBOSE            Set to '1' or 'true' for verbose output
    HOP3_VERSION            Install specific version
    HOP3_GIT                Set to '1' or 'true' to install from git
    HOP3_SKIP_DEPS          Set to '1' or 'true' to skip dependencies
    HOP3_SKIP_NGINX         Set to '1' or 'true' to skip nginx
    HOP3_SKIP_POSTGRES      Set to '1' or 'true' to skip PostgreSQL

Examples:
    # Install latest version
    curl -LsSf https://hop3.cloud/install-server.sh | sudo bash

    # Install from git (latest development version)
    curl -LsSf https://hop3.cloud/install-server.sh | sudo bash -s -- --git

    # Install specific version
    curl -LsSf https://hop3.cloud/install-server.sh | sudo bash -s -- --version 0.4.0

    # Install without PostgreSQL
    curl -LsSf https://hop3.cloud/install-server.sh | sudo bash -s -- --skip-postgres

Supported Distributions:
    - Debian / Ubuntu
    - Fedora / RHEL / CentOS
    - Arch Linux
EOF
}

# =============================================================================
# Root Check
# =============================================================================

check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        log_error "This installer must be run as root."
        log_error ""
        log_error "Please run with sudo:"
        log_error "  curl -LsSf https://hop3.cloud/install-server.sh | sudo bash"
        exit 1
    fi
}

# =============================================================================
# OS Detection
# =============================================================================

detect_os() {
    OS="$(uname -s)"
    case "$OS" in
        Linux)
            log_info "Detected OS: Linux"

            # Detect distribution
            if [ -f /etc/os-release ]; then
                . /etc/os-release
                log_info "Distribution: $NAME"
            fi
            ;;
        Darwin)
            log_error "macOS is not supported for server installation."
            log_error "Hop3 Server requires a Linux server."
            exit 1
            ;;
        *)
            log_error "Unsupported operating system: $OS"
            log_error "Hop3 Server requires a Linux server."
            exit 1
            ;;
    esac
}

# =============================================================================
# Python Detection
# =============================================================================

find_python() {
    # Try python3 first, then python
    for cmd in python3 python; do
        if command -v "$cmd" >/dev/null 2>&1; then
            PYTHON="$cmd"
            return 0
        fi
    done

    log_error "Python not found."
    log_error ""
    log_error "Please install Python ${MIN_PYTHON_VERSION_MAJOR}.${MIN_PYTHON_VERSION_MINOR} or later:"
    log_error ""

    if command -v apt >/dev/null 2>&1; then
        log_error "  sudo apt update && sudo apt install python3 python3-venv"
    elif command -v dnf >/dev/null 2>&1; then
        log_error "  sudo dnf install python3"
    elif command -v pacman >/dev/null 2>&1; then
        log_error "  sudo pacman -S python"
    else
        log_error "  Install Python using your system's package manager"
    fi

    exit 1
}

check_python_version() {
    log_info "Checking Python version..."

    # Get Python version
    VERSION_OUTPUT=$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)

    if [ -z "$VERSION_OUTPUT" ]; then
        log_error "Could not determine Python version."
        exit 1
    fi

    MAJOR=$(echo "$VERSION_OUTPUT" | cut -d. -f1)
    MINOR=$(echo "$VERSION_OUTPUT" | cut -d. -f2)

    log_info "Found Python $VERSION_OUTPUT"

    # Check version
    if [ "$MAJOR" -lt "$MIN_PYTHON_VERSION_MAJOR" ]; then
        version_error
    elif [ "$MAJOR" -eq "$MIN_PYTHON_VERSION_MAJOR" ] && [ "$MINOR" -lt "$MIN_PYTHON_VERSION_MINOR" ]; then
        version_error
    fi

    log_success "Python version is compatible."
}

version_error() {
    log_error "Python ${MIN_PYTHON_VERSION_MAJOR}.${MIN_PYTHON_VERSION_MINOR} or later is required."
    log_error "Found: Python $VERSION_OUTPUT"
    log_error ""
    log_error "Please upgrade Python:"

    if command -v apt >/dev/null 2>&1; then
        log_error "  sudo apt update && sudo apt install python3"
    elif command -v dnf >/dev/null 2>&1; then
        log_error "  sudo dnf install python3"
    elif command -v pacman >/dev/null 2>&1; then
        log_error "  sudo pacman -S python"
    fi

    exit 1
}

# =============================================================================
# Check venv module
# =============================================================================

check_venv_module() {
    log_info "Checking for venv module..."

    if ! "$PYTHON" -c 'import venv' 2>/dev/null; then
        log_error "Python venv module is not installed."
        log_error ""
        log_error "Please install the venv module:"

        if command -v apt >/dev/null 2>&1; then
            log_error "  sudo apt install python3-venv"
        elif command -v dnf >/dev/null 2>&1; then
            log_error "  sudo dnf install python3-venv"
        elif command -v pacman >/dev/null 2>&1; then
            log_error "  (venv is included with Python on Arch)"
        fi

        exit 1
    fi

    log_success "venv module is available."
}

# =============================================================================
# Download Installer
# =============================================================================

download_installer() {
    # Check for local installer first (for testing)
    if [ -n "$LOCAL_INSTALLER" ]; then
        if [ -f "$LOCAL_INSTALLER" ]; then
            log_info "Using local installer: $LOCAL_INSTALLER"
            cp "$LOCAL_INSTALLER" "$INSTALLER_PATH"
            log_success "Installer copied from local path."
            return 0
        else
            log_error "Local installer not found: $LOCAL_INSTALLER"
            exit 1
        fi
    fi

    log_info "Downloading Python installer..."

    # Try curl first, then wget
    if command -v curl >/dev/null 2>&1; then
        if ! curl -fsSL "$INSTALLER_URL" -o "$INSTALLER_PATH" 2>/dev/null; then
            log_error "Failed to download installer with curl."
            log_error "URL: $INSTALLER_URL"
            log_error ""
            log_error "Please check your network connection and try again."
            exit 1
        fi
    elif command -v wget >/dev/null 2>&1; then
        if ! wget -q "$INSTALLER_URL" -O "$INSTALLER_PATH" 2>/dev/null; then
            log_error "Failed to download installer with wget."
            log_error "URL: $INSTALLER_URL"
            exit 1
        fi
    else
        log_error "Neither curl nor wget is available."
        log_error "Please install curl or wget and try again."
        exit 1
    fi

    log_success "Installer downloaded."
}

# =============================================================================
# Cleanup
# =============================================================================

cleanup() {
    if [ -f "$INSTALLER_PATH" ]; then
        rm -f "$INSTALLER_PATH"
    fi
}

# Set up cleanup trap
trap cleanup EXIT

# =============================================================================
# Main
# =============================================================================

main() {
    # Check for help flag first
    for arg in "$@"; do
        case "$arg" in
            --help|-h)
                usage
                exit 0
                ;;
        esac
    done

    echo ""
    printf "${BOLD}Hop3 Server Installer${RESET}\n"
    echo "========================================"
    echo ""

    # Pre-flight checks
    check_root
    detect_os
    find_python
    check_python_version
    check_venv_module

    # Download and run the Python installer
    download_installer

    log_info "Running Python installer..."
    echo ""

    # Build extra arguments from environment variables
    EXTRA_ARGS=""
    if [ -n "${HOP3_LOCAL_PACKAGE:-}" ]; then
        EXTRA_ARGS="--local-path $HOP3_LOCAL_PACKAGE"
    fi

    # Execute the Python installer with all arguments passed through
    # shellcheck disable=SC2086
    exec "$PYTHON" "$INSTALLER_PATH" $EXTRA_ARGS "$@"
}

main "$@"
