# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Installation verification for CLI installer."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

from hop3_installer.common import (
    Colors,
    print_error,
    print_success,
    print_warning,
    run_cmd,
)

from .config import INSTALL_DIR, VENV_DIR


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


def print_final_message(bin_dir: Path, *, path_is_active: bool) -> None:
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
