# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Hop3 CLI Installer.

A single-file installer for the Hop3 CLI tool.
Uses only Python standard library for maximum portability.

Usage:
    curl -LsSf https://hop3.cloud/install-cli.py | python3 -
    curl -LsSf https://hop3.cloud/install-cli.py | python3 - --git
    python3 install-cli.py --help
"""

from __future__ import annotations

import argparse
import shutil
import sys
import urllib.request
from pathlib import Path

from hop3_installer.common import (
    Colors,
    CommandError,
    Spinner,
    check_python_version,
    cmd_exists,
    get_current_shell,
    print_detail,
    print_error,
    print_header,
    print_info,
    print_step,
    print_success,
    print_warning,
    run_cmd,
)

from .config import (
    CLI_COMMANDS,
    DEFAULT_BIN_DIR,
    DEFAULT_BRANCH,
    GIT_REPO,
    GIT_SUBDIR,
    INSTALL_DIR,
    PACKAGE_NAME,
    SHELL_CONFIGS,
    VENV_DIR,
    CLIInstallerConfig,
)

# =============================================================================
# System Checks
# =============================================================================


def check_venv() -> bool:
    """Check if venv module is available."""
    try:
        import venv  # noqa: F401

        return True
    except ImportError:
        return False


def check_git() -> bool:
    """Check if git is available."""
    return cmd_exists("git")


# =============================================================================
# Installation Functions
# =============================================================================


def check_existing_installation(force: bool) -> bool:
    """Check for existing installation.

    Returns:
        True if should proceed with installation, False if already installed
    """
    if VENV_DIR.exists():
        if force:
            print_info("Existing installation found, will reinstall (--force)")
            return True
        print_warning("Hop3 CLI is already installed")
        print_detail(f"Location: {INSTALL_DIR}")
        print_detail("Use --force to reinstall")
        return False
    return True


def create_virtual_environment() -> None:
    """Create a Python virtual environment."""
    # Create install directory
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)

    # Remove existing venv if present
    if VENV_DIR.exists():
        shutil.rmtree(VENV_DIR)

    # Try creating venv with pip first (faster if ensurepip is available)
    with Spinner("Creating virtual environment..."):
        result = run_cmd(
            [sys.executable, "-m", "venv", str(VENV_DIR)],
            check=False,
        )

    if result.returncode == 0:
        print_success(f"Virtual environment created at {VENV_DIR}")
        return

    # Fallback: create venv without pip, then bootstrap pip manually
    # This works on systems where python3-venv is installed but ensurepip is not
    print_info("ensurepip not available, bootstrapping pip manually...")

    # Remove failed venv attempt
    if VENV_DIR.exists():
        shutil.rmtree(VENV_DIR)

    with Spinner("Creating virtual environment (without pip)..."):
        run_cmd([sys.executable, "-m", "venv", "--without-pip", str(VENV_DIR)])

    # Download and run get-pip.py
    get_pip_url = "https://bootstrap.pypa.io/get-pip.py"
    get_pip_path = INSTALL_DIR / "get-pip.py"

    with Spinner("Downloading pip installer..."):
        urllib.request.urlretrieve(get_pip_url, get_pip_path)

    venv_python = VENV_DIR / "bin" / "python"
    with Spinner("Installing pip..."):
        run_cmd([str(venv_python), str(get_pip_path), "--quiet"])

    # Clean up
    get_pip_path.unlink(missing_ok=True)

    print_success(f"Virtual environment created at {VENV_DIR}")


def install_package(config: CLIInstallerConfig) -> None:
    """Install the hop3-cli package."""
    pip = str(VENV_DIR / "bin" / "pip")

    # Upgrade pip first
    with Spinner("Upgrading pip..."):
        run_cmd([pip, "install", "--upgrade", "pip"])

    # Determine what to install
    if config.local_path:
        package_spec = config.local_path
        source_desc = f"local path ({config.local_path})"
    elif config.use_git:
        # Install uv for build backend
        with Spinner("Installing build tools..."):
            run_cmd([pip, "install", "uv"])
        package_spec = f"git+{GIT_REPO}@{config.branch}#subdirectory={GIT_SUBDIR}"
        source_desc = f"git ({config.branch} branch)"
    elif config.version:
        package_spec = f"{PACKAGE_NAME}=={config.version}"
        source_desc = f"PyPI (version {config.version})"
    else:
        package_spec = PACKAGE_NAME
        source_desc = "PyPI (latest)"

    # Install the package
    with Spinner(f"Installing hop3-cli from {source_desc}..."):
        cmd = [pip, "install", package_spec]
        if config.verbose:
            run_cmd(cmd, capture=False)
        else:
            run_cmd(cmd)

    print_success("hop3-cli installed successfully")


def create_command_symlinks(bin_dir: Path) -> int:
    """Create symlinks for CLI commands.

    Returns:
        Count of created links
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    count = 0

    for cmd in CLI_COMMANDS:
        source = VENV_DIR / "bin" / cmd
        target = bin_dir / cmd

        if not source.exists():
            continue

        # Remove existing
        if target.exists() or target.is_symlink():
            target.unlink()

        # Create symlink
        try:
            target.symlink_to(source)
            print_success(f"Created symlink: {target}")
            count += 1
        except OSError:
            # Fallback to copy
            shutil.copy2(source, target)
            print_info(f"Copied command (symlink failed): {target}")
            count += 1

    return count


def update_shell_config(bin_dir: Path, modify_path: bool) -> bool:
    """Update shell configuration if needed.

    Returns:
        True if PATH is already active in current session
    """
    import os

    # Check if already in PATH
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    path_is_active = str(bin_dir) in path_dirs

    if path_is_active:
        print_success("PATH already configured")
        return True

    if not modify_path:
        print_warning(f"Add {bin_dir} to your PATH manually")
        return False

    # Detect shell and update config
    shell = get_current_shell()
    if not shell or shell not in SHELL_CONFIGS:
        print_warning(f'Add this to your shell config: export PATH="{bin_dir}:$PATH"')
        return False

    config_file = SHELL_CONFIGS[shell]
    marker = "# Added by Hop3 CLI installer"

    # Check if already added to config file
    config_has_path = False
    if config_file.exists():
        content = config_file.read_text()
        config_has_path = marker in content

    if not config_has_path:
        # Add PATH export
        if shell == "fish":
            line = f"\n{marker}\nfish_add_path {bin_dir}\n"
        else:
            line = f'\n{marker}\nexport PATH="{bin_dir}:$PATH"\n'

        with Path(config_file).open("a") as f:
            f.write(line)
        print_success(f"Updated {config_file}")
    else:
        print_info("Shell config already updated")

    # PATH is in config but not active in current session
    print_warning(f"To use hop3 now, run: source {config_file}")
    print_detail("Or start a new terminal session")
    return False


def verify_installation() -> bool:
    """Verify the installation works."""
    hop3 = VENV_DIR / "bin" / "hop3"
    if not hop3.exists():
        hop3 = VENV_DIR / "bin" / "hop"

    if not hop3.exists():
        print_error("Command not found in virtual environment")
        return False

    try:
        result = run_cmd([str(hop3), "--help"], check=False)
        if result.returncode == 0:
            print_success("Installation verified")
            return True
    except Exception:
        pass

    print_warning("Command exists but returned an error")
    return True  # Still consider it installed


def print_final_message(bin_dir: Path, path_is_active: bool) -> None:
    """Print success message with next steps."""
    print()
    print(f"{Colors.GREEN}{Colors.BOLD}Installation complete!{Colors.RESET}")
    print()
    print(f"  {Colors.BOLD}Commands:{Colors.RESET}  hop3, hop")
    print(f"  {Colors.BOLD}Location:{Colors.RESET}  {INSTALL_DIR}")
    print()
    print(f"  {Colors.BOLD}Get started:{Colors.RESET}")
    if path_is_active:
        print("    hop3 --help           Show available commands")
        print("    hop3 auth:login       Log in to your Hop3 server")
    else:
        # Show full path since hop3 isn't in PATH yet
        print(f"    {bin_dir}/hop3 --help")
        print()
        print(f"  {Colors.BOLD}Or reload your shell first:{Colors.RESET}")
        print("    source ~/.bashrc      (then use 'hop3' directly)")
    print()
    print(f"  {Colors.BOLD}To uninstall:{Colors.RESET}")
    print(f"    rm -rf {INSTALL_DIR}")
    print(f"    rm -f {bin_dir}/hop3 {bin_dir}/hop")
    print()


# =============================================================================
# CLI Argument Parsing
# =============================================================================


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    # Get defaults from environment
    env_config = CLIInstallerConfig.from_env()

    parser = argparse.ArgumentParser(
        prog="install-cli.py",
        description="Install the Hop3 CLI tool.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 install-cli.py                    Install latest version from PyPI
  python3 install-cli.py --git              Install from git (main branch)
  python3 install-cli.py --git --branch dev Install from git (dev branch)
  python3 install-cli.py --version 0.4.0    Install specific version
  python3 install-cli.py --force            Force reinstall

Environment Variables:
  HOP3_VERSION          Install specific version
  HOP3_GIT              Install from git (1 or true)
  HOP3_BRANCH           Git branch (default: main)
  HOP3_LOCAL_PACKAGE    Install from local path
  HOP3_FORCE            Force reinstall (1 or true)
  HOP3_NO_MODIFY_PATH   Don't modify shell config (1 or true)
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
        "--bin-dir",
        metavar="PATH",
        type=Path,
        default=env_config.bin_dir,
        help=f"Directory for command symlinks (default: {DEFAULT_BIN_DIR})",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        default=env_config.force,
        help="Force reinstall even if already installed",
    )

    parser.add_argument(
        "--no-modify-path",
        action="store_true",
        default=env_config.no_modify_path,
        help="Don't modify shell configuration files",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        default=env_config.verbose,
        help="Show verbose output",
    )

    return parser


# =============================================================================
# Main
# =============================================================================


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    # Check Python version first
    check_python_version()

    parser = create_parser()
    args = parser.parse_args()

    # Convert args to config
    config = CLIInstallerConfig(
        version=args.version,
        use_git=args.git,
        branch=args.branch,
        local_path=args.local_path,
        bin_dir=args.bin_dir,
        force=args.force,
        no_modify_path=args.no_modify_path,
        verbose=args.verbose,
    )

    # Header
    print_header("Hop3 CLI Installer")

    total_steps = 5

    # Step 1: System checks
    print_step(1, total_steps, "Checking system requirements...")

    python_version = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    print_success(f"Python {python_version}")

    if not check_venv():
        print_error("Python venv module not found")
        print_detail("Install with: sudo apt install python3-venv")
        return 1
    print_success("venv module available")

    if config.use_git and not config.local_path and not check_git():
        print_error("Git not found (required for --git)")
        print_detail("Install with: sudo apt install git")
        return 1

    # Check existing installation
    if not check_existing_installation(config.force):
        return 0

    # Step 2: Create virtual environment
    print_step(2, total_steps, "Creating virtual environment...")

    try:
        create_virtual_environment()
    except CommandError as e:
        print_error("Failed to create virtual environment")
        error_output = e.stderr.strip() or e.stdout.strip()
        if error_output:
            for line in error_output.split("\n"):
                if line.strip():
                    print_detail(line.strip())
        else:
            print_detail(f"Command: {' '.join(e.cmd)}")
            print_detail(f"Exit code: {e.returncode}")
        print()
        print_info("Possible fixes:")
        print_detail("1. Check disk space: df -h ~/.hop3-cli")
        print_detail("2. Check permissions: ls -la ~/.hop3-cli")
        print_detail("3. Check network access (needed to download pip)")
        return 1

    # Step 3: Install package
    print_step(3, total_steps, "Installing hop3-cli...")

    try:
        install_package(config)
    except CommandError as e:
        print_error("Failed to install hop3-cli")
        if config.verbose:
            print_detail(e.stderr)
        if config.use_git:
            print_detail("Make sure git is installed and you have network access")
        else:
            print_detail("Try --git to install from the git repository")
        return 1

    # Step 4: Create symlinks
    print_step(4, total_steps, "Creating command symlinks...")

    count = create_command_symlinks(config.bin_dir)
    if count == 0:
        print_warning("No commands found to symlink")

    # Step 5: Update PATH
    print_step(5, total_steps, "Configuring PATH...")

    path_is_active = update_shell_config(config.bin_dir, not config.no_modify_path)

    # Verify
    print()
    if not verify_installation():
        print_warning("Installation may have issues")

    # Success message
    print_final_message(config.bin_dir, path_is_active)

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
