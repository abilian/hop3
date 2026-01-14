# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands."""

from __future__ import annotations

import importlib.metadata
import pathlib
import platform
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import ClassVar

from hop3.config import HOP3_ROOT
from hop3.core.plugins import get_plugin_manager
from hop3.lib.logging import DEFAULT_LOG_FILE
from hop3.lib.registry import register

from ._base import Command


@register
class SystemCmd(Command):
    """Manage the hop3 system."""

    name: ClassVar[str] = "system"


@register
class UptimeCmd(Command):
    """Show host server uptime."""

    name: ClassVar[str] = "system:uptime"

    def call(self, *args):
        result = subprocess.run(
            ["uptime"], capture_output=True, text=True, check=False
        ).stdout
        return [{"t": "text", "text": result}]


@register
class PSCmd(Command):
    """List all server processes."""

    name: ClassVar[str] = "system:ps"

    def call(self, *args):
        result = subprocess.run(
            ["ps", "aux"], capture_output=True, text=True, check=False
        ).stdout
        return [{"t": "text", "text": result}]


@register
class StatusCmd(Command):
    """Show Hop3 system status."""

    name: ClassVar[str] = "system:status"

    def call(self, *args):
        version = importlib.metadata.version("hop3_server")

        return [
            {"t": "text", "text": f"Hop3 version: {version}"},
        ]


@register
class InfoCmd(Command):
    """Show detailed Hop3 system information.

    Use --verbose or -v for more details including loaded plugins.
    """

    name: ClassVar[str] = "system:info"

    def call(self, *args, **kwargs):
        # Parse --verbose/-v from args
        verbose = "--verbose" in args or "-v" in args

        version = importlib.metadata.version("hop3_server")
        python_version = sys.version.split()[0]
        os_info = f"{platform.system()} {platform.release()}"

        lines = [
            "Hop3 System Information",
            "=" * 40,
            f"Version:        {version}",
            f"Python:         {python_version}",
            f"Platform:       {os_info}",
        ]

        # Check Docker availability
        docker_available = self._check_docker()
        lines.append(
            f"Docker:         {'available' if docker_available else 'not available'}"
        )

        if verbose:
            lines.extend(self._get_verbose_info())

        return [{"t": "text", "text": "\n".join(lines)}]

    def _check_docker(self) -> bool:
        """Check if Docker is available."""
        try:
            result = subprocess.run(
                ["docker", "version", "--format", "{{.Server.Version}}"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _get_verbose_info(self) -> list[str]:
        """Get verbose information including plugins."""
        lines = [
            "",
            "Loaded Plugins",
            "-" * 40,
        ]

        pm = get_plugin_manager()

        # Get builders
        builder_classes = []
        for sublist in pm.hook.get_builders():
            builder_classes.extend(sublist)
        if builder_classes:
            lines.append("Builders:")
            for cls in builder_classes:
                lines.append(f"  - {cls.__name__}")
        else:
            lines.append("Builders: (none loaded)")

        # Get deployers
        deployer_classes = []
        for sublist in pm.hook.get_deployers():
            deployer_classes.extend(sublist)
        if deployer_classes:
            lines.append("Deployers:")
            for cls in deployer_classes:
                # Try to get the 'name' attribute if it exists
                name = getattr(cls, "name", cls.__name__)
                lines.append(f"  - {cls.__name__} (runtime: {name})")
        else:
            lines.append("Deployers: (none loaded)")

        # Get toolchains
        toolchain_classes = []
        for sublist in pm.hook.get_toolchains():
            toolchain_classes.extend(sublist)
        if toolchain_classes:
            lines.append("Toolchains:")
            for cls in toolchain_classes:
                lines.append(f"  - {cls.__name__}")
        else:
            lines.append("Toolchains: (none loaded)")

        # Check important paths
        lines.extend([
            "",
            "Paths",
            "-" * 40,
        ])
        lines.append(f"HOP3_ROOT:      {HOP3_ROOT}")
        lines.append(f"Apps dir:       {HOP3_ROOT / 'apps'}")
        lines.append(f"Nginx conf:     {HOP3_ROOT / 'nginx'}")

        return lines

        # registries = result["registries"]
        # print("Configured registries:")
        # for reg in sorted(registries, key=itemgetter("priority")):
        #     msg = (
        #         f'  priority: {reg["priority"]:>2}   '
        #         f'format: {reg["format"]:<16}   '
        #         f'url: {reg["url"]}'
        #     )
        #     print(msg)


@register
class SystemLogsCmd(Command):
    """Show Hop3 server logs.

    Usage: hop3 system:logs [options]

    Options:
        -n, --lines N      Number of lines to show (default: 100)
        --since DURATION   Show logs since duration (e.g., 1h, 30m, 1d)
        --level LEVEL      Filter by log level (DEBUG, INFO, WARNING, ERROR)
        --grep PATTERN     Filter lines matching pattern
        -f, --follow       Follow log output (not yet implemented)

    Examples:
        hop3 system:logs                    # Last 100 lines
        hop3 system:logs -n 50              # Last 50 lines
        hop3 system:logs --since 1h         # Last hour
        hop3 system:logs --level ERROR      # Errors only
        hop3 system:logs --grep deploy      # Lines containing 'deploy'
    """

    name: ClassVar[str] = "system:logs"

    def call(self, *args, **kwargs):
        # Parse options from args (CLI passes them as positional strings)
        parsed = self._parse_args(args)
        lines = parsed.get("lines", 100)
        since = parsed.get("since")
        level = parsed.get("level", "").upper()
        grep = parsed.get("grep", "")

        # Check if log file exists
        if not DEFAULT_LOG_FILE.exists():
            return [{"t": "text", "text": f"No log file found at {DEFAULT_LOG_FILE}"}]

        # Read log file
        with pathlib.Path(DEFAULT_LOG_FILE).open(encoding="utf-8") as f:
            all_lines = f.readlines()

        # Apply --since filter
        if since:
            cutoff = self._parse_since(since)
            if cutoff:
                all_lines = self._filter_by_time(all_lines, cutoff)

        # Apply --level filter
        if level:
            all_lines = [ln for ln in all_lines if f"[{level}]" in ln]

        # Apply --grep filter
        if grep:
            pattern = re.compile(grep, re.IGNORECASE)
            all_lines = [ln for ln in all_lines if pattern.search(ln)]

        # Take last N lines
        result_lines = all_lines[-lines:]

        if not result_lines:
            return [{"t": "text", "text": "No log entries found matching criteria."}]

        return [{"t": "text", "text": "".join(result_lines)}]

    def _parse_since(self, since: str):
        """Parse duration string like '1h', '30m', '1d' into a cutoff datetime."""
        match = re.match(r"^(\d+)([smhd])$", since.lower())
        if not match:
            return None

        value = int(match.group(1))
        unit = match.group(2)

        delta = {
            "s": timedelta(seconds=value),
            "m": timedelta(minutes=value),
            "h": timedelta(hours=value),
            "d": timedelta(days=value),
        }.get(unit)

        if delta:
            return datetime.now(tz=timezone.utc) - delta
        return None

    def _filter_by_time(self, lines: list[str], cutoff) -> list[str]:
        """Filter log lines to only include those after cutoff time."""
        result = []
        for line in lines:
            # Log format: "2025-12-07 10:15:23 [LEVEL] message"
            if len(line) >= 19:
                try:
                    timestamp_str = line[:19]
                    timestamp = datetime.strptime(
                        timestamp_str, "%Y-%m-%d %H:%M:%S"
                    ).replace(tzinfo=timezone.utc)
                    if timestamp >= cutoff:
                        result.append(line)
                except ValueError:
                    # Line doesn't start with valid timestamp, include it anyway
                    # (could be continuation of previous log entry)
                    if result:  # Only if we've started collecting
                        result.append(line)
        return result

    def _parse_args(self, args: tuple) -> dict:
        """Parse CLI arguments into a dictionary.

        Handles:
            -n 50, --lines 50, --lines=50
            --since 1h, --since=1h
            --level ERROR, --level=ERROR
            --grep pattern, --grep=pattern
        """
        result = {}
        args_list = list(args)
        i = 0

        while i < len(args_list):
            arg = args_list[i]

            # Handle -n shorthand
            if arg == "-n" and i + 1 < len(args_list):
                result["lines"] = int(args_list[i + 1])
                i += 2
                continue

            # Handle --key=value format
            if arg.startswith("--") and "=" in arg:
                key, value = arg[2:].split("=", 1)
                if key == "lines":
                    result[key] = int(value)
                else:
                    result[key] = value
                i += 1
                continue

            # Handle --key value format
            if arg.startswith("--") and i + 1 < len(args_list):
                key = arg[2:]
                value = args_list[i + 1]
                if key == "lines":
                    result[key] = int(value)
                else:
                    result[key] = value
                i += 2
                continue

            i += 1

        return result


#
#
# class SettingsSubcommand(Command):
#     """Show server settings."""
#
#     name = "server settings"
#
#     def run(self):
#         result = client.call("settings")
#         pp(result)
#
#
# class CleanupSubcommand(Command):
#     """Cleanup server (remove inactive docker images and containers)."""
#
#     name = "server cleanup"
#
#     # TODO: ask for confirmation
#
#     def run(self):
#         result = client.ssh("docker system prune -af")
#         result = client.ssh("docker volume prune -f")
#         print(result.stdout)
