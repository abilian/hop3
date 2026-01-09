# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Shell configuration and symlink management for CLI installer."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from hop3_installer.common import (
    get_current_shell,
    print_detail,
    print_info,
    print_success,
    print_warning,
)

from .config import CLI_COMMANDS, SHELL_CONFIGS, VENV_DIR


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


def update_shell_config(bin_dir: Path, *, modify_path: bool) -> bool:
    """Update shell configuration if needed.

    Returns:
        True if PATH is already active in current session
    """
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
