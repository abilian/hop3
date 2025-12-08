# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Display functions for demo launcher."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lib.context import OutputLevel
from lib.discovery import DEMOS_DIR, discover_demos, get_demo_info
from lib.output import bold, cyan, dim

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from lib.context import DemoContext


def print_banner(output_level: int) -> None:
    """Print the demo banner."""
    if output_level < 2:  # SILENT or QUIET
        return

    banner = """
    HOP3 DEMOS
    ==========

    Hop3 Demo Launcher
    """
    print(cyan(bold(banner)))


def print_config(ctx: DemoContext, demos: list[str]) -> None:
    """Print demo configuration."""
    if ctx.output_level < OutputLevel.NORMAL:
        return

    print(bold("Configuration:"))
    print(f"  Server:          {ctx.server_ip}")
    print(f"  SSH Target:      {ctx.ssh_target}")
    print(f"  Admin User:      {ctx.admin_user}")
    print(f"  Demos to run:    {', '.join(demos)}")
    print(f"  Local code:      {ctx.use_local_code}")
    print(f"  Skip install:    {ctx.skip_install}")
    print(f"  Keep apps:       {ctx.no_cleanup}")
    print()


def list_demos(demo_dirs: Sequence[Path] | None = None) -> None:
    """List available demos and exit."""
    demos = discover_demos(demo_dirs)

    print(bold("Available demos:"))
    print()
    if demos:
        for name, (title, _desc, location) in demos.items():
            # Show location if not in main demos dir
            loc_suffix = ""
            if location.parent != DEMOS_DIR:
                loc_suffix = f" ({location.parent})"
            print(f"  {cyan(f'{name:12}')}  {title}{loc_suffix}")
    else:
        print("  (no demos found)")
    print()
    print(dim("You can also specify external paths to Hop3 applications."))
    print()


def show_inventory(demo_dirs: Sequence[Path] | None = None) -> None:
    """Show detailed inventory of all demos."""
    demos = discover_demos(demo_dirs)

    print(cyan(bold("Demo Inventory")))
    print("=" * 70)
    print()

    if not demos:
        print("  (no demos found)")
        return

    for name, (_title, _description, location) in demos.items():
        info = get_demo_info(name, location)
        if not info:
            continue

        print(f"{bold(name)}: {info.title}")
        print(f"  {dim('Location:')} {info.location}")

        if info.is_symlink and info.symlink_target:
            print(f"  {dim('Symlink to:')} {info.symlink_target}")

        if info.description:
            print(f"  {dim('Description:')} {info.description}")

        if info.app_name:
            print(f"  {dim('App name:')} {info.app_name}")

        if info.hostname:
            print(f"  {dim('Hostname:')} {info.hostname}")

        print(f"  {dim('App type:')} {info.app_type}")
        print(f"  {dim('Files:')} {', '.join(info.files[:8])}", end="")
        if len(info.files) > 8:
            print(f" (+{len(info.files) - 8} more)")
        else:
            print()
        print()

    print(f"Total: {len(demos)} demos")
