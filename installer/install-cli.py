#!/usr/bin/env python3
# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Hop3 CLI Installer

A single-file installer for the Hop3 CLI tool.
Uses only Python standard library for maximum portability.

Usage:
    curl -LsSf https://hop3.cloud/install-cli.py | python3 -
    curl -LsSf https://hop3.cloud/install-cli.py | python3 - --git
    python3 install-cli.py --help
"""

from __future__ import annotations

# =============================================================================
# Version Check (must run before any 3.10+ features are used at runtime)
# =============================================================================
import sys

MIN_PYTHON = (3, 10)

if sys.version_info < MIN_PYTHON:
    print(f"Error: Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required")
    print(f"Found: Python {sys.version_info.major}.{sys.version_info.minor}")
    print()
    print("Please install a newer Python version:")
    print("  Ubuntu/Debian: sudo apt install python3.11")
    print("  Fedora:        sudo dnf install python3.11")
    print("  macOS:         brew install python@3.11")
    sys.exit(1)

# =============================================================================
# Imports (standard library only)
# =============================================================================

import argparse
import itertools
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

# =============================================================================
# Configuration
# =============================================================================

PACKAGE_NAME = "hop3-cli"
GIT_REPO = "https://github.com/abilian/hop3.git"
GIT_SUBDIR = "packages/hop3-cli"
DEFAULT_BRANCH = "main"

INSTALL_DIR = Path.home() / ".hop3-cli"
VENV_DIR = INSTALL_DIR / "venv"
DEFAULT_BIN_DIR = Path.home() / ".local" / "bin"

CLI_COMMANDS = ["hop3", "hop"]

SHELL_CONFIGS = {
    "bash": Path.home() / ".bashrc",
    "zsh": Path.home() / ".zshrc",
    "fish": Path.home() / ".config" / "fish" / "config.fish",
}

# =============================================================================
# Terminal Output
# =============================================================================


class Colors:
    """ANSI color codes."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[0;33m"
    BLUE = "\033[0;34m"
    CYAN = "\033[0;36m"

    @classmethod
    def disable(cls) -> None:
        for attr in ["RESET", "BOLD", "DIM", "RED", "GREEN", "YELLOW", "BLUE", "CYAN"]:
            setattr(cls, attr, "")


# Disable colors if not a TTY
if not sys.stdout.isatty():
    Colors.disable()


def print_header(title: str) -> None:
    """Print a styled header."""
    print()
    print(f"{Colors.BOLD}{Colors.CYAN}{title}{Colors.RESET}")
    print(f"{Colors.DIM}{'=' * len(title)}{Colors.RESET}")
    print()


def print_step(step: int, total: int, message: str) -> None:
    """Print a step indicator."""
    print(f"{Colors.BOLD}[{step}/{total}]{Colors.RESET} {message}")


def print_success(message: str) -> None:
    """Print a success message."""
    print(f"      {Colors.GREEN}✓{Colors.RESET} {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    print(f"      {Colors.BLUE}ℹ{Colors.RESET} {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    print(f"      {Colors.YELLOW}⚠{Colors.RESET} {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    print(f"      {Colors.RED}✗{Colors.RESET} {message}", file=sys.stderr)


def print_detail(message: str) -> None:
    """Print a detail/sub-item."""
    print(f"        {Colors.DIM}{message}{Colors.RESET}")


# =============================================================================
# Spinner for Long Operations
# =============================================================================


class Spinner:
    """A simple terminal spinner for long-running operations."""

    CHARS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, message: str):
        self.message = message
        self.spinning = False
        self.thread: threading.Thread | None = None

    def __enter__(self) -> Spinner:
        if sys.stdout.isatty():
            self.spinning = True
            self.thread = threading.Thread(target=self._spin, daemon=True)
            self.thread.start()
        else:
            print(f"      ... {self.message}")
        return self

    def __exit__(self, *args) -> None:
        self.spinning = False
        if self.thread:
            self.thread.join(timeout=0.5)
        if sys.stdout.isatty():
            # Clear the spinner line
            print(f"\r{' ' * (len(self.message) + 10)}\r", end="")

    def _spin(self) -> None:
        for char in itertools.cycle(self.CHARS):
            if not self.spinning:
                break
            print(
                f"\r      {Colors.CYAN}{char}{Colors.RESET} {self.message}",
                end="",
                flush=True,
            )
            time.sleep(0.08)


# =============================================================================
# Command Execution
# =============================================================================


class CommandError(Exception):
    """Raised when a command fails."""

    def __init__(self, cmd: list[str], returncode: int, stderr: str, stdout: str = ""):
        self.cmd = cmd
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = stdout
        super().__init__(f"Command failed: {' '.join(cmd)}")


def run_cmd(
    cmd: list[str],
    capture: bool = True,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    result = subprocess.run(
        cmd,
        check=False,
        capture_output=capture,
        text=True,
        env=run_env,
    )

    if check and result.returncode != 0:
        raise CommandError(
            cmd, result.returncode, result.stderr or "", result.stdout or ""
        )

    return result


def cmd_exists(cmd: str) -> bool:
    """Check if a command exists in PATH."""
    return shutil.which(cmd) is not None


# =============================================================================
# System Checks
# =============================================================================


def check_python() -> str:
    """Check Python version. Returns version string."""
    version = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    return version


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


def get_current_shell() -> str | None:
    """Detect the current shell."""
    shell = os.environ.get("SHELL", "")
    if "zsh" in shell:
        return "zsh"
    if "fish" in shell:
        return "fish"
    if "bash" in shell:
        return "bash"
    return None


# =============================================================================
# Installation Functions
# =============================================================================


def check_existing_installation(force: bool) -> bool:
    """Check for existing installation. Returns True if should proceed."""
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
    import urllib.request

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


def install_package(
    version: str | None,
    use_git: bool,
    branch: str,
    local_path: str | None,
    verbose: bool,
) -> None:
    """Install the hop3-cli package."""
    pip = str(VENV_DIR / "bin" / "pip")

    # Upgrade pip first
    with Spinner("Upgrading pip..."):
        run_cmd([pip, "install", "--upgrade", "pip"])

    # Determine what to install
    if local_path:
        package_spec = local_path
        source_desc = f"local path ({local_path})"
    elif use_git:
        # Install uv for build backend
        with Spinner("Installing build tools..."):
            run_cmd([pip, "install", "uv"])
        package_spec = f"git+{GIT_REPO}@{branch}#subdirectory={GIT_SUBDIR}"
        source_desc = f"git ({branch} branch)"
    elif version:
        package_spec = f"{PACKAGE_NAME}=={version}"
        source_desc = f"PyPI (version {version})"
    else:
        package_spec = PACKAGE_NAME
        source_desc = "PyPI (latest)"

    # Install the package
    with Spinner(f"Installing hop3-cli from {source_desc}..."):
        cmd = [pip, "install", package_spec]
        if verbose:
            run_cmd(cmd, capture=False)
        else:
            run_cmd(cmd)

    print_success("hop3-cli installed successfully")


def create_command_symlinks(bin_dir: Path) -> int:
    """Create symlinks for CLI commands. Returns count of created links."""
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
            print_success(f"Copied command: {target}")
            count += 1

    return count


def update_shell_config(bin_dir: Path, modify_path: bool) -> bool:
    """Update shell configuration if needed. Returns True if PATH is active."""
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

        with open(config_file, "a") as f:
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
        default=os.environ.get("HOP3_VERSION"),
        help="Install a specific version (e.g., 0.4.0)",
    )

    parser.add_argument(
        "--git",
        action="store_true",
        default=os.environ.get("HOP3_GIT", "").lower() in ("1", "true"),
        help="Install from git repository",
    )

    parser.add_argument(
        "--branch",
        metavar="BRANCH",
        default=os.environ.get("HOP3_BRANCH", DEFAULT_BRANCH),
        help=f"Git branch to install from (default: {DEFAULT_BRANCH})",
    )

    parser.add_argument(
        "--local-path",
        metavar="PATH",
        default=os.environ.get("HOP3_LOCAL_PACKAGE"),
        help="Install from a local directory",
    )

    parser.add_argument(
        "--bin-dir",
        metavar="PATH",
        type=Path,
        default=Path(os.environ.get("HOP3_BIN_DIR", str(DEFAULT_BIN_DIR))),
        help=f"Directory for command symlinks (default: {DEFAULT_BIN_DIR})",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        default=os.environ.get("HOP3_FORCE", "").lower() in ("1", "true"),
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
        help="Show verbose output",
    )

    return parser


# =============================================================================
# Main
# =============================================================================


def main() -> int:
    """Main entry point. Returns exit code."""
    parser = create_parser()
    args = parser.parse_args()

    # Header
    print_header("Hop3 CLI Installer")

    total_steps = 5

    # Step 1: System checks
    print_step(1, total_steps, "Checking system requirements...")

    python_version = check_python()
    print_success(f"Python {python_version}")

    if not check_venv():
        print_error("Python venv module not found")
        print_detail("Install with: sudo apt install python3-venv")
        return 1
    print_success("venv module available")

    if args.git and not args.local_path and not check_git():
        print_error("Git not found (required for --git)")
        print_detail("Install with: sudo apt install git")
        return 1

    # Check existing installation
    if not check_existing_installation(args.force):
        return 0

    # Step 2: Create virtual environment
    print()
    print_step(2, total_steps, "Creating virtual environment...")

    try:
        create_virtual_environment()
    except CommandError as e:
        print_error("Failed to create virtual environment")
        # Show the most useful error info
        error_output = e.stderr.strip() or e.stdout.strip()
        if error_output:
            for line in error_output.split("\n"):
                if line.strip():
                    print_detail(line.strip())
        else:
            print_detail(f"Command: {' '.join(e.cmd)}")
            print_detail(f"Exit code: {e.returncode}")
        # Provide helpful suggestions
        print()
        print_info("Possible fixes:")
        print_detail("1. Check disk space: df -h ~/.hop3-cli")
        print_detail("2. Check permissions: ls -la ~/.hop3-cli")
        print_detail("3. Check network access (needed to download pip)")
        return 1

    # Step 3: Install package
    print()
    print_step(3, total_steps, "Installing hop3-cli...")

    try:
        install_package(
            version=args.version,
            use_git=args.git,
            branch=args.branch,
            local_path=args.local_path,
            verbose=args.verbose,
        )
    except CommandError as e:
        print_error("Failed to install hop3-cli")
        if args.verbose:
            print_detail(e.stderr)
        if args.git:
            print_detail("Make sure git is installed and you have network access")
        else:
            print_detail("Try --git to install from the git repository")
        return 1

    # Step 4: Create symlinks
    print()
    print_step(4, total_steps, "Creating command symlinks...")

    count = create_command_symlinks(args.bin_dir)
    if count == 0:
        print_warning("No commands found to symlink")

    # Step 5: Update PATH
    print()
    print_step(5, total_steps, "Configuring PATH...")

    path_is_active = update_shell_config(args.bin_dir, not args.no_modify_path)

    # Verify
    print()
    if not verify_installation():
        print_warning("Installation may have issues")

    # Success message
    print_final_message(args.bin_dir, path_is_active)

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
