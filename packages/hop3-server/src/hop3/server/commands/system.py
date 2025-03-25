# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands."""

from __future__ import annotations

import importlib.metadata
import subprocess

from hop3.lib.decorators import command
from .base import Command


@command
class SystemCommand(Command):
    """Manage the hop3 system."""

    name = "system"

    hide_from_help = True

    def subcommands(self) -> list[Command]:
        return [
            UptimeSubcommand(),
            PsSubcommand(),
            StatusSubcommand(),
        ]


@command
class UptimeSubcommand(Command):
    """Show host server uptime."""

    name = "uptime"

    def call(self, *args):
        result = subprocess.run(
            ["uptime"], capture_output=True, text=True, check=False
        ).stdout
        return [{"t": "text", "text": result}]


@command
class PsSubcommand(Command):
    """List all server processes."""

    name = "ps"

    def call(self, *args):
        result = subprocess.run(
            ["ps", "aux"], capture_output=True, text=True, check=False
        ).stdout
        return [{"t": "text", "text": result}]


@command
class StatusSubcommand(Command):
    """Show Hop3 system status."""

    name = "status"

    def call(self, *args):
        version = importlib.metadata.version("hop3_server")

        return [
            {"t": "text", "text": f"Hop3 version: {version}"},
        ]

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
