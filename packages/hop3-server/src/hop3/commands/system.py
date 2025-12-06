# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands."""

from __future__ import annotations

import importlib.metadata
import platform
import subprocess
import sys
from typing import ClassVar

from hop3.core.plugins import get_plugin_manager
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
        from hop3.config import HOP3_ROOT

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


# class LogsSubcommand(Command):
#     """Show system logs."""
#
#     name = "logs"
#
#     arguments = [
#         Argument("service", help="Service to show logs for"),
#     ]
#
#     def run(self, service: str):
#         if not service:
#             print("Service must be one of: nua, letsencrypt, nginx")
#
#         match service:
#             case "nua":
#                 print("Showing Nua logs [TODO]")
#             case "letsencrypt":
#                 result = client.ssh("cat log/letsencrypt/letsencrypt.log")
#                 print(result.stdout)
#             case "nginx":
#                 print("Showing Nginx logs [TODO]")
#             case _:
#                 raise BadArgumentError(
#                     "Service must be one of: nua, letsencrypt, nginx"
#                 )
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
