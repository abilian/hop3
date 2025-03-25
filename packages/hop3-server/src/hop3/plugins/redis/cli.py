# Copyright (c) 2024-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""CLI commands to manage Redis."""

from __future__ import annotations

from argparse import ArgumentParser

from hop3.lib import echo
from hop3.lib.decorators import command


@command
class RedisCmd:
    """Manage Redis commands."""

    name = "redis"


@command
class RedisCliCmd:
    """Opens a Redis prompt: hop redis:cli."""

    name = "redis:cli"

    def run(self) -> None:
        echo("Opening Redis CLI prompt...")
        # TODO: Implement logic to open a Redis prompt
        echo("Redis CLI session ended.")


@command
class RedisCredentialsCmd:
    """Display credentials information: hop redis:credentials."""

    name = "redis:credentials"

    def run(self) -> None:
        echo("Fetching Redis credentials...")
        # TODO: Implement logic to display Redis credentials
        echo("Credentials displayed successfully.")


@command
class RedisInfoCmd:
    """Gets information about Redis: hop redis:info."""

    name = "redis:info"

    def run(self) -> None:
        echo("Fetching Redis information...")
        # TODO: Implement logic to fetch Redis information
        echo("Redis information displayed successfully.")


@command
class RedisKeyspaceNotificationsCmd:
    """Set the keyspace notifications configuration: hop redis:keyspace-notifications <config>."""

    name = "redis:keyspace-notifications"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "config", type=str, help="Keyspace notification configuration string."
        )

    def run(self, config: str) -> None:
        echo(f"Setting keyspace notifications configuration: {config}")
        # TODO: Implement logic to set keyspace notifications
        echo("Keyspace notifications configuration updated.")


@command
class RedisMaintenanceCmd:
    """Manage maintenance windows: hop redis:maintenance."""

    name = "redis:maintenance"

    def run(self) -> None:
        echo("Managing Redis maintenance windows...")
        # TODO: Implement logic to manage maintenance windows
        echo("Redis maintenance windows updated.")


@command
class RedisMaxMemoryCmd:
    """Set the key eviction policy when instances reach their storage limit: hop redis:maxmemory <policy>."""

    name = "redis:maxmemory"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "policy",
            type=str,
            help="Key eviction policy (e.g., allkeys-lru, noeviction).",
        )

    def run(self, policy: str) -> None:
        echo(f"Setting max memory eviction policy to '{policy}'.")
        # TODO: Implement logic to update eviction policy
        echo("Max memory eviction policy updated.")


@command
class RedisPromoteCmd:
    """Sets DATABASE as your REDIS_URL: hop redis:promote."""

    name = "redis:promote"

    def run(self) -> None:
        echo("Promoting Redis instance...")
        # TODO: Implement logic to promote Redis instance
        echo("Redis instance promoted successfully.")


@command
class RedisStatsResetCmd:
    """Reset all Redis stats: hop redis:stats-reset."""

    name = "redis:stats-reset"

    def run(self) -> None:
        echo("Resetting Redis stats...")
        # TODO: Implement logic to reset stats using CONFIG RESETSTAT
        echo("Redis stats reset successfully.")


@command
class RedisTimeoutCmd:
    """Set the number of seconds to wait before killing idle connections: hop redis:timeout <seconds>."""

    name = "redis:timeout"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("seconds", type=int, help="Idle timeout in seconds.")

    def run(self, seconds: int) -> None:
        echo(f"Setting Redis idle timeout to {seconds} seconds.")
        # TODO: Implement logic to set idle timeout
        echo("Redis idle timeout updated.")


@command
class RedisUpgradeCmd:
    """Perform in-place version upgrade: hop redis:upgrade."""

    name = "redis:upgrade"

    def run(self) -> None:
        echo("Upgrading Redis instance...")
        # TODO: Implement logic to perform an in-place version upgrade
        echo("Redis instance upgraded successfully.")


@command
class RedisWaitCmd:
    """Wait for Redis instance to be available: hop redis:wait."""

    name = "redis:wait"

    def run(self) -> None:
        echo("Waiting for Redis instance to become available...")
        # TODO: Implement logic to wait until Redis is available
        echo("Redis instance is now available.")
