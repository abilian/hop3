#!/bin/sh
# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
#
# Hop3 CLI Installer Bootstrap Script
#
# This script performs minimal environment validation and downloads
# the Python installer to do the actual work.
#
# Usage:
#   curl -LsSf https://hop3.cloud/install-cli.sh | bash
#   curl -LsSf https://hop3.cloud/install-cli.sh | bash -s -- --git
#   curl -LsSf https://hop3.cloud/install-cli.sh | bash -s -- --version 0.4.0
#
# Environment variables:
#   HOP3_FORCE_REINSTALL  Force reinstall (1 or true)
#   HOP3_NO_MODIFY_PATH   Don't modify shell config (1 or true)
#   HOP3_VERBOSE          Enable verbose output (1 or true)
#   HOP3_VERSION          Install specific version
#   HOP3_GIT              Install from git (1 or true)
#   HOP3_BIN_DIR          Custom binary directory
#   HOP3_LOCAL_PACKAGE    Local package directory (for testing)

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

INSTALLER_URL="${HOP3_INSTALLER_URL:-https://hop3.cloud/install-cli.py}"
INSTALLER_PATH="/tmp/hop3-install-cli.py"
MIN_PYTHON_VERSION_MAJOR=3
MIN_PYTHON_VERSION_MINOR=10

# For local testing: set HOP3_LOCAL_INSTALLER to the path of install-cli.py
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
Hop3 CLI Installer

Usage:
    curl -LsSf https://hop3.cloud/install-cli.sh | bash
    curl -LsSf https://hop3.cloud/install-cli.sh | bash -s -- [OPTIONS]

Options:
    --force             Force reinstall even if already installed
    --no-modify-path    Don't modify shell configuration files
    --verbose           Enable verbose output
    --version VERSION   Install a specific version (e.g., 0.4.0)
    --git               Install from git (head of main branch)
    --local-path PATH   Install from a local directory
    --bin-dir PATH      Custom binary directory (default: ~/.local/bin)
    --help              Show this help message

Environment Variables:
    HOP3_FORCE_REINSTALL    Set to '1' or 'true' to force reinstall
    HOP3_NO_MODIFY_PATH     Set to '1' or 'true' to skip PATH modification
    HOP3_VERBOSE            Set to '1' or 'true' for verbose output
    HOP3_VERSION            Install specific version
    HOP3_GIT                Set to '1' or 'true' to install from git
    HOP3_LOCAL_PACKAGE      Local package directory (for testing)
    HOP3_BIN_DIR            Custom binary directory

Examples:
    # Install latest version
    curl -LsSf https://hop3.cloud/install-cli.sh | bash

    # Install from git (latest development version)
    curl -LsSf https://hop3.cloud/install-cli.sh | bash -s -- --git

    # Install specific version
    curl -LsSf https://hop3.cloud/install-cli.sh | bash -s -- --version 0.4.0

    # Force reinstall with verbose output
    curl -LsSf https://hop3.cloud/install-cli.sh | bash -s -- --force --verbose
EOF
}

# =============================================================================
# OS Detection
# =============================================================================

detect_os() {
    OS="$(uname -s)"
    case "$OS" in
        Linux)
            log_info "Detected OS: Linux"
            ;;
        Darwin)
            log_info "Detected OS: macOS"
            ;;
        MINGW*|MSYS*|CYGWIN*)
            log_error "Windows is not supported by this installer."
            log_error "Please use WSL2 or install manually."
            exit 1
            ;;
        *)
            log_error "Unsupported operating system: $OS"
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

    case "$(uname -s)" in
        Linux)
            if command -v apt >/dev/null 2>&1; then
                log_error "  sudo apt update && sudo apt install python3 python3-venv"
            elif command -v dnf >/dev/null 2>&1; then
                log_error "  sudo dnf install python3"
            elif command -v pacman >/dev/null 2>&1; then
                log_error "  sudo pacman -S python"
            else
                log_error "  Install Python using your system's package manager"
            fi
            ;;
        Darwin)
            log_error "  brew install python@3.12"
            log_error "  or download from https://www.python.org/downloads/"
            ;;
    esac

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

    case "$(uname -s)" in
        Linux)
            if command -v apt >/dev/null 2>&1; then
                log_error "  sudo apt update && sudo apt install python3"
            elif command -v dnf >/dev/null 2>&1; then
                log_error "  sudo dnf install python3"
            fi
            ;;
        Darwin)
            log_error "  brew upgrade python"
            ;;
    esac

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

        case "$(uname -s)" in
            Linux)
                if command -v apt >/dev/null 2>&1; then
                    log_error "  sudo apt install python3-venv"
                elif command -v dnf >/dev/null 2>&1; then
                    log_error "  sudo dnf install python3-venv"
                elif command -v pacman >/dev/null 2>&1; then
                    log_error "  (venv is included with Python on Arch)"
                fi
                ;;
            Darwin)
                log_error "  (venv should be included with Python from Homebrew)"
                log_error "  Try: brew reinstall python"
                ;;
        esac

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
    printf "${BOLD}Hop3 CLI Installer${RESET}\n"
    echo "========================================"
    echo ""

    # Pre-flight checks
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
