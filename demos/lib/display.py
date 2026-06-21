# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Display functions for demo launcher."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lib.context import OutputLevel
from lib.discovery import DEMOS_DIR, discover_demos, get_demo_info, select_demos
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
    print(f"  Preflight:       {ctx.preflight}")
    print(f"  Clean before:    {ctx.clean_before}")
    print(f"  Keep apps:       {ctx.no_cleanup}")
    print()


def list_demos(
    demo_dirs: Sequence[Path] | None = None,
    *,
    verbose: bool = False,
    select: Sequence[str] | None = None,
    skip: Sequence[str] | None = None,
) -> None:
    """List available demos, optionally filtered by feature tags.

    With ``verbose`` (the old ``--inventory``), show full details + the
    namespaced capability tags for each demo.
    """
    demos = discover_demos(demo_dirs)
    titles = {name: title for name, (title, _d, _loc) in demos.items()}
    items = [(name, loc, False) for name, (_t, _d, loc) in demos.items()]
    total = len(items)
    if select or skip:
        items = select_demos(items, select or [], skip or [])

    if not items:
        msg = "(no demos found)" if not total else "(no demos match the filter)"
        print(bold("Available demos:"))
        print(f"\n  {msg}\n")
        return

    if verbose:
        _list_demos_verbose(items)
    else:
        _list_demos_compact(items, titles)

    shown, suffix = len(items), ""
    if shown != total:
        suffix = f" (of {total}; filtered by --select/--skip)"
    print(f"Total: {shown} demos{suffix}")


def _list_demos_compact(items, titles: dict[str, str]) -> None:
    print(bold("Available demos:"))
    print()
    for name, location, _ in items:
        loc_suffix = "" if location.parent == DEMOS_DIR else f" ({location.parent})"
        print(f"  {cyan(f'{name:12}')}  {titles.get(name, name)}{loc_suffix}")
    print()
    print(dim("Use 'list -v' for tags/details; external paths work too."))
    print()


def _list_demos_verbose(items) -> None:
    print(cyan(bold("Demo Inventory")))
    print("=" * 70)
    print()
    for name, location, _ in items:
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
        print(f"  {dim('App type:')} {info.app_type}")
        if info.app_tags:
            print(f"  {dim('Tags:')} {cyan('  '.join(info.app_tags))}")
        files = ", ".join(info.files[:8])
        extra = f" (+{len(info.files) - 8} more)" if len(info.files) > 8 else ""
        print(f"  {dim('Files:')} {files}{extra}")
        print()
