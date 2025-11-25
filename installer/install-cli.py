#!/usr/bin/env python3
# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Hop3 CLI Installer.

This script installs the Hop3 CLI tool by:
1. Creating a virtual environment at ~/.hop3-cli/venv
2. Installing the hop3-cli package
3. Creating symlinks in ~/.local/bin for 'hop3' and 'hop' commands
4. Optionally updating shell configuration for PATH

Usage:
    python install-cli.py [OPTIONS]

Options:
    --force             Force reinstall even if already installed
    --no-modify-path    Don't modify shell configuration files
    --verbose           Enable verbose output
    --version VERSION   Install a specific version (e.g., 0.4.0)
    --git               Install from git (head of main branch)
    --bin-dir PATH      Custom binary directory (default: ~/.local/bin)
    --help              Show this help message
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# =============================================================================
# Configuration
# =============================================================================

INSTALL_DIR = Path.home() / ".hop3-cli"
VENV_DIR = INSTALL_DIR / "venv"
DEFAULT_BIN_DIR = Path.home() / ".local" / "bin"

PACKAGE_NAME = "hop3-cli"
GIT_URL = "git+https://github.com/abilian/hop3.git@main#subdirectory=packages/hop3-cli"

CLI_COMMANDS = ["hop3", "hop"]

# Shell configuration files
SHELL_CONFIGS = {
    "bash": Path.home() / ".bashrc",
    "zsh": Path.home() / ".zshrc",
    "fish": Path.home() / ".config" / "fish" / "config.fish",
}

# Path export line (marker comment helps identify our addition)
PATH_EXPORT_MARKER = "# Added by Hop3 CLI installer"
PATH_EXPORT_BASH = 'export PATH="$HOME/.local/bin:$PATH"'
PATH_EXPORT_FISH = "fish_add_path $HOME/.local/bin"

# =============================================================================
# Terminal Colors
# =============================================================================


class Colors:
    """ANSI color codes for terminal output."""

    RESET = "\033[0m"
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[0;33m"
    BLUE = "\033[0;34m"
    BOLD = "\033[1m"

    @classmethod
    def disable(cls) -> None:
        """Disable colors (for non-TTY output)."""
        cls.RESET = ""
        cls.RED = ""
        cls.GREEN = ""
        cls.YELLOW = ""
        cls.BLUE = ""
        cls.BOLD = ""


# Disable colors if not a TTY
if not sys.stdout.isatty():
    Colors.disable()


# =============================================================================
# Logging Functions
# =============================================================================

VERBOSE = False


def log_info(message: str) -> None:
    """Print an info message."""
    print(f"{Colors.BLUE}[INFO]{Colors.RESET} {message}")


def log_success(message: str) -> None:
    """Print a success message."""
    print(f"{Colors.GREEN}[OK]{Colors.RESET} {message}")


def log_warning(message: str) -> None:
    """Print a warning message."""
    print(f"{Colors.YELLOW}[WARN]{Colors.RESET} {message}")


def log_error(message: str) -> None:
    """Print an error message to stderr."""
    print(f"{Colors.RED}[ERROR]{Colors.RESET} {message}", file=sys.stderr)


def log_debug(message: str) -> None:
    """Print a debug message (only in verbose mode)."""
    if VERBOSE:
        print(f"{Colors.BLUE}[DEBUG]{Colors.RESET} {message}")


# =============================================================================
# Utility Functions
# =============================================================================


def run_command(
    cmd: list[str],
    check: bool = True,
    capture_output: bool = False,
    env: dict | None = None,
) -> subprocess.CompletedProcess:
    """Run a command and handle errors."""
    log_debug(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            check=check,
            capture_output=capture_output,
            text=True,
            env=env,
        )
        return result
    except subprocess.CalledProcessError as e:
        log_error(f"Command failed: {' '.join(cmd)}")
        if e.stdout:
            log_error(f"stdout: {e.stdout}")
        if e.stderr:
            log_error(f"stderr: {e.stderr}")
        raise


def get_current_shell() -> str:
    """Detect the user's current shell."""
    shell = os.environ.get("SHELL", "")
    if "zsh" in shell:
        return "zsh"
    if "fish" in shell:
        return "fish"
    if "bash" in shell:
        return "bash"
    # Default to bash
    return "bash"


# =============================================================================
# Installation Steps
# =============================================================================


def check_existing_installation(force: bool) -> bool:
    """Check if Hop3 CLI is already installed.

    Returns True if we should proceed with installation.
    """
    hop3_bin = VENV_DIR / "bin" / "hop3"
    if hop3_bin.exists():
        if force:
            log_info("Existing installation found. Forcing reinstall...")
            return True
        log_warning("Hop3 CLI is already installed.")
        log_info("Use --force to reinstall.")
        return False
    return True


def create_install_directory() -> None:
    """Create the installation directory."""
    log_info(f"Creating installation directory: {INSTALL_DIR}")
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)


def create_virtual_environment() -> None:
    """Create a Python virtual environment."""
    log_info(f"Creating virtual environment: {VENV_DIR}")

    if VENV_DIR.exists():
        log_debug("Removing existing virtual environment...")
        shutil.rmtree(VENV_DIR)

    try:
        run_command([sys.executable, "-m", "venv", str(VENV_DIR)])
    except subprocess.CalledProcessError:
        log_error("Failed to create virtual environment.")
        log_error("Make sure the 'venv' module is installed.")
        log_error("On Debian/Ubuntu: sudo apt install python3-venv")
        log_error("On Fedora: sudo dnf install python3-venv")
        sys.exit(1)

    log_success("Virtual environment created.")


def install_hop3_cli(version: str | None, use_git: bool) -> None:
    """Install the hop3-cli package into the virtual environment."""
    pip_path = VENV_DIR / "bin" / "pip"

    # Upgrade pip first
    log_info("Upgrading pip...")
    run_command([str(pip_path), "install", "--upgrade", "pip"], capture_output=True)

    # Determine what to install
    if use_git:
        log_info("Installing hop3-cli from git (main branch)...")
        package_spec = GIT_URL
    elif version:
        log_info(f"Installing hop3-cli version {version}...")
        package_spec = f"{PACKAGE_NAME}=={version}"
    else:
        log_info("Installing hop3-cli (latest version)...")
        package_spec = PACKAGE_NAME

    # Install the package
    try:
        run_command(
            [str(pip_path), "install", package_spec],
            capture_output=not VERBOSE,
        )
    except subprocess.CalledProcessError:
        log_error("Failed to install hop3-cli.")
        if use_git:
            log_error("Make sure git is installed and you have network access.")
        else:
            log_error("The package may not be available on PyPI yet.")
            log_error("Try using --git to install from the git repository.")
        sys.exit(1)

    log_success("hop3-cli installed successfully.")


def expose_cli_commands(bin_dir: Path) -> None:
    """Create symlinks to the CLI commands in the bin directory."""
    log_info(f"Creating command symlinks in {bin_dir}")

    # Create bin directory if it doesn't exist
    bin_dir.mkdir(parents=True, exist_ok=True)

    exposed_count = 0
    for cmd in CLI_COMMANDS:
        source = VENV_DIR / "bin" / cmd
        target = bin_dir / cmd

        if not source.exists():
            log_debug(f"Source command not found: {source} (skipping)")
            continue

        # Remove existing symlink or file
        if target.exists() or target.is_symlink():
            log_debug(f"Removing existing {target}")
            target.unlink()

        # Try to create symlink, fall back to copy
        try:
            target.symlink_to(source)
            log_debug(f"Created symlink: {target} -> {source}")
            exposed_count += 1
        except OSError:
            # Symlinks may not work on some systems, copy instead
            log_debug(f"Symlink failed, copying {source} to {target}")
            shutil.copy2(source, target)
            exposed_count += 1

    if exposed_count == 0:
        log_warning("No CLI commands were found to expose.")
    else:
        log_success(f"CLI commands exposed ({exposed_count} command(s)).")


def update_shell_path(bin_dir: Path, modify_path: bool) -> None:
    """Update shell configuration to include bin_dir in PATH."""
    if not modify_path:
        log_info("Skipping PATH modification (--no-modify-path).")
        return

    # Check if bin_dir is already in PATH
    current_path = os.environ.get("PATH", "")
    if str(bin_dir) in current_path.split(os.pathsep):
        log_info(f"{bin_dir} is already in PATH.")
        return

    shell = get_current_shell()
    config_file = SHELL_CONFIGS.get(shell)

    if not config_file:
        log_warning(f"Unknown shell: {shell}. Please add {bin_dir} to your PATH manually.")
        return

    # Check if we've already modified this file
    if config_file.exists():
        content = config_file.read_text()
        if PATH_EXPORT_MARKER in content:
            log_info(f"PATH already configured in {config_file}")
            return

    # Determine the export line based on shell
    if shell == "fish":
        export_line = f"\n{PATH_EXPORT_MARKER}\n{PATH_EXPORT_FISH}\n"
    else:
        export_line = f"\n{PATH_EXPORT_MARKER}\n{PATH_EXPORT_BASH}\n"

    log_info(f"Adding PATH to {config_file}")

    # Create parent directory if needed (for fish)
    config_file.parent.mkdir(parents=True, exist_ok=True)

    # Append to the config file
    with config_file.open("a") as f:
        f.write(export_line)

    log_success(f"Updated {config_file}")


def verify_installation() -> bool:
    """Verify that the installation was successful."""
    log_info("Verifying installation...")

    # Try hop3 first, fall back to hop
    hop3_bin = VENV_DIR / "bin" / "hop3"
    hop_bin = VENV_DIR / "bin" / "hop"

    if hop3_bin.exists():
        verify_bin = hop3_bin
    elif hop_bin.exists():
        verify_bin = hop_bin
    else:
        log_error("Neither hop3 nor hop command found in virtual environment.")
        return False

    try:
        result = run_command(
            [str(verify_bin), "help"],
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            log_success("Installation verified successfully.")
            return True
        log_warning(f"{verify_bin.name} command exists but returned an error.")
        log_debug(f"Output: {result.stdout}")
        log_debug(f"Error: {result.stderr}")
        return True  # Still consider it a success
    except Exception as e:
        log_error(f"Failed to verify installation: {e}")
        return False


def print_success_message(bin_dir: Path) -> None:
    """Print success message with usage instructions."""
    print()
    print(f"{Colors.GREEN}{Colors.BOLD}Hop3 CLI installed successfully!{Colors.RESET}")
    print()
    print("Installation locations:")
    print(f"  - Virtual environment: {VENV_DIR}")
    print(f"  - Commands: {bin_dir}/hop3, {bin_dir}/hop")
    print()
    print("You may need to restart your shell or run:")
    shell = get_current_shell()
    config_file = SHELL_CONFIGS.get(shell, Path("~/.bashrc"))
    print(f"  source {config_file}")
    print()
    print("Get started:")
    print("  hop3 help              Show available commands")
    print("  hop3 auth:login        Log in to your Hop3 server")
    print("  hop3 apps              List your applications")
    print()


def print_uninstall_instructions() -> None:
    """Print uninstall instructions."""
    print(f"{Colors.BOLD}To uninstall Hop3 CLI:{Colors.RESET}")
    print(f"  rm -rf {INSTALL_DIR}")
    print(f"  rm -f {DEFAULT_BIN_DIR}/hop3 {DEFAULT_BIN_DIR}/hop")
    print("  # Optionally remove the PATH line from your shell config")
    print()


# =============================================================================
# Argument Parsing
# =============================================================================


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Install the Hop3 CLI tool.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python install-cli.py                    Install latest version
  python install-cli.py --git              Install from git (main branch)
  python install-cli.py --version 0.4.0    Install specific version
  python install-cli.py --force            Force reinstall
        """,
    )

    parser.add_argument(
        "--force",
        action="store_true",
        default=os.environ.get("HOP3_FORCE_REINSTALL", "").lower() in ("1", "true"),
        help="Force reinstall even if already installed",
    )

    parser.add_argument(
        "--no-modify-path",
        action="store_true",
        default=os.environ.get("HOP3_NO_MODIFY_PATH", "").lower() in ("1", "true"),
        help="Don't modify shell configuration files",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        default=os.environ.get("HOP3_VERBOSE", "").lower() in ("1", "true"),
        help="Enable verbose output",
    )

    parser.add_argument(
        "--version",
        type=str,
        default=os.environ.get("HOP3_VERSION"),
        help="Install a specific version (e.g., 0.4.0)",
    )

    parser.add_argument(
        "--git",
        action="store_true",
        default=os.environ.get("HOP3_GIT", "").lower() in ("1", "true"),
        help="Install from git (head of main branch)",
    )

    parser.add_argument(
        "--bin-dir",
        type=Path,
        default=Path(os.environ.get("HOP3_BIN_DIR", str(DEFAULT_BIN_DIR))),
        help=f"Custom binary directory (default: {DEFAULT_BIN_DIR})",
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

    print()
    print(f"{Colors.BOLD}Hop3 CLI Installer{Colors.RESET}")
    print("=" * 40)
    print()

    # Check for existing installation
    if not check_existing_installation(args.force):
        sys.exit(0)

    # Run installation steps
    create_install_directory()
    create_virtual_environment()
    install_hop3_cli(args.version, args.git)
    expose_cli_commands(args.bin_dir)
    update_shell_path(args.bin_dir, not args.no_modify_path)

    # Verify and report
    if not verify_installation():
        log_error("Installation verification failed.")
        sys.exit(1)

    print_success_message(args.bin_dir)
    print_uninstall_instructions()


if __name__ == "__main__":
    main()
