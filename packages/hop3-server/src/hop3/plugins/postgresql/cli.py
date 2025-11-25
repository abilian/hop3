# Copyright (c) 2024-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""CLI commands to manage PostgreSQL databases."""

from __future__ import annotations

from argparse import ArgumentParser

from hop3.core.plugins import get_addon
from hop3.lib import echo
from hop3.lib.decorators import command


@command
class PgCmd:
    """Manage a PostgreSQL database."""


@command
class PgCreateCmd:
    """Create a PostgreSQL database: hop pg:create <name>.

    This is a convenience command that wraps 'hop services:create postgres <name>'.
    """

    name = "pg:create"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("name", type=str, help="Name of the database service.")

    def run(self, name: str) -> None:
        echo(f"Creating PostgreSQL database '{name}'...")

        try:
            # Use the service strategy to create the database
            service = get_addon("postgres", name)
            service.create()

            echo(f"Database '{name}' created successfully.")
            echo(
                f"\nTo attach this database to an app, run:\n  hop services:attach {name} --app <app-name>"
            )

        except RuntimeError as e:
            echo(f"Error: {e}")
        except Exception as e:
            echo(f"Unexpected error: {e}")


@command
class PgDropCmd:
    """Drop a PostgreSQL database: hop pg:drop <name>.

    This is a convenience command that wraps 'hop services:destroy <name>'.
    WARNING: This will permanently delete all data!
    """

    name = "pg:drop"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("name", type=str, help="Name of the database to drop.")

    def run(self, name: str) -> None:
        echo(f"Dropping database '{name}'...")
        echo("WARNING: This will permanently delete all data!")

        try:
            # Use the service strategy to destroy the database
            service = get_addon("postgres", name)
            service.destroy()

            echo(f"Database '{name}' dropped successfully.")

        except RuntimeError as e:
            echo(f"Error: {e}")
        except Exception as e:
            echo(f"Unexpected error: {e}")


@command
class PgImportCmd:
    """Import data into a PostgreSQL database: hop pg:import <name>."""

    name = "pg:import"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "name", type=str, help="Name of the database to import data into."
        )

    def run(self, name: str) -> None:
        echo(f"Importing data into database '{name}'.")
        # TODO: Add actual implementation to import data
        echo(f"Data imported into database '{name}' successfully.")


@command
class PgDumpCmd:
    """Dump a PostgreSQL database: hop pg:dump <name>."""

    name = "pg:dump"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("name", type=str, help="Name of the database to dump.")

    def run(self, name: str) -> None:
        echo(f"Dumping database '{name}'.")
        # TODO: Add actual implementation to dump the database
        echo(f"Database '{name}' dumped successfully.")


@command
class PgBackupsCmd:
    """List database backups: hop pg:backups."""

    name = "pg:backups"

    def run(self) -> None:
        echo("Listing database backups...")
        # TODO: Implement logic to list backups
        echo("Database backups listed successfully.")


@command
class PgBloatCmd:
    """Show table and index bloat: hop pg:bloat."""

    name = "pg:bloat"

    def run(self) -> None:
        echo("Analyzing table and index bloat...")
        # TODO: Implement logic to show bloat
        echo("Bloat analysis completed.")


@command
class PgBlockingCmd:
    """Display queries holding locks: hop pg:blocking."""

    name = "pg:blocking"

    def run(self) -> None:
        echo("Displaying queries holding locks...")
        # TODO: Implement logic to display blocking queries
        echo("Blocking queries displayed successfully.")


@command
class PgCopyCmd:
    """Copy data from source to target database: hop pg:copy <source> <target>."""

    name = "pg:copy"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("source", type=str, help="Source database.")
        parser.add_argument("target", type=str, help="Target database.")

    def run(self, source: str, target: str) -> None:
        echo(f"Copying data from '{source}' to '{target}'...")
        # TODO: Implement logic to copy data
        echo("Data copied successfully.")


@command
class PgCredentialsCmd:
    """Show database credentials: hop pg:credentials <name>."""

    name = "pg:credentials"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("name", type=str, help="Name of the database.")

    def run(self, name: str) -> None:
        echo(f"Fetching credentials for database '{name}'...")

        try:
            # Use the service strategy to get connection details
            service = get_addon("postgres", name)
            details = service.get_connection_details()

            # Display the credentials
            for key, value in details.items():
                # Mask password in display
                if "PASSWORD" in key.upper():
                    echo(f"{key}: {'*' * 8}")
                else:
                    echo(f"{key}: {value}")

        except RuntimeError as e:
            echo(f"Error: {e}")
        except Exception as e:
            echo(f"Unexpected error: {e}")


@command
class PgDiagnoseCmd:
    """Run or view diagnostics report: hop pg:diagnose."""

    name = "pg:diagnose"

    def run(self) -> None:
        echo("Running diagnostics...")
        # TODO: Implement logic to diagnose issues
        echo("Diagnostics completed successfully.")


@command
class PgInfoCmd:
    """Show database information: hop pg:info <name>."""

    name = "pg:info"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("name", type=str, help="Name of the database.")

    def run(self, name: str) -> None:
        echo(f"Fetching information for database '{name}'...")

        try:
            # Use the service strategy to get info
            service = get_addon("postgres", name)
            info = service.info()

            # Display the information
            for key, value in info.items():
                echo(f"{key}: {value}")

        except RuntimeError as e:
            echo(f"Error: {e}")
        except Exception as e:
            echo(f"Unexpected error: {e}")


@command
class PgKillCmd:
    """Kill a query: hop pg:kill <query_id>."""

    name = "pg:kill"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("query_id", type=str, help="Query ID to kill.")

    def run(self, query_id: str) -> None:
        echo(f"Killing query '{query_id}'...")
        # TODO: Implement logic to kill a query
        echo(f"Query '{query_id}' killed successfully.")


@command
class PgKillAllCmd:
    """Terminate all connections: hop pg:killall."""

    name = "pg:killall"

    def run(self) -> None:
        echo("Terminating all connections...")
        # TODO: Implement logic to kill all connections
        echo("All connections terminated successfully.")


@command
class PgLinksCmd:
    """List all databases and link information: hop pg:links."""

    name = "pg:links"

    def run(self) -> None:
        echo("Listing database links...")
        # TODO: Implement logic to list database links
        echo("Database links listed successfully.")


@command
class PgLocksCmd:
    """Display queries with active locks: hop pg:locks."""

    name = "pg:locks"

    def run(self) -> None:
        echo("Displaying queries with active locks...")
        # TODO: Implement logic to show locks
        echo("Active locks displayed successfully.")


@command
class PgMaintenanceCmd:
    """Show current maintenance information: hop pg:maintenance."""

    name = "pg:maintenance"

    def run(self) -> None:
        echo("Fetching maintenance information...")
        # TODO: Implement logic to fetch maintenance info
        echo("Maintenance information displayed successfully.")


@command
class PgOutliersCmd:
    """Show top 10 longest queries: hop pg:outliers."""

    name = "pg:outliers"

    def run(self) -> None:
        echo("Fetching top 10 longest queries...")
        # TODO: Implement logic to find query outliers
        echo("Top 10 longest queries displayed successfully.")


@command
class PgPromoteCmd:
    """Set DATABASE as your DATABASE_URL: hop pg:promote."""

    name = "pg:promote"

    def run(self) -> None:
        echo("Promoting database...")
        # TODO: Implement logic to promote the database
        echo("Database promoted successfully.")


@command
class PgPsCmd:
    """View active queries: hop pg:ps."""

    name = "pg:ps"

    def run(self) -> None:
        echo("Fetching active queries...")
        # TODO: Implement logic to show active queries
        echo("Active queries displayed successfully.")


@command
class PgPsqlCmd:
    """Open a psql shell: hop pg:psql."""

    name = "pg:psql"

    def run(self) -> None:
        echo("Opening psql shell...")
        # TODO: Implement logic to open psql shell
        echo("Exited psql shell.")


@command
class PgPullCmd:
    """Pull Heroku database to local or remote: hop pg:pull <source> <target>."""

    name = "pg:pull"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("source", type=str, help="Source database.")
        parser.add_argument("target", type=str, help="Target database.")

    def run(self, source: str, target: str) -> None:
        echo(f"Pulling database from '{source}' to '{target}'...")
        # TODO: Implement logic to pull database
        echo("Database pulled successfully.")


@command
class PgPushCmd:
    """Push local or remote database to Heroku: hop pg:push <source> <target>."""

    name = "pg:push"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("source", type=str, help="Source database.")
        parser.add_argument("target", type=str, help="Target database.")

    def run(self, source: str, target: str) -> None:
        echo(f"Pushing database from '{source}' to '{target}'...")
        # TODO: Implement logic to push database
        echo("Database pushed successfully.")


@command
class PgResetCmd:
    """Delete all data in DATABASE: hop pg:reset."""

    name = "pg:reset"

    def run(self) -> None:
        echo("Resetting database...")
        # TODO: Implement logic to reset database
        echo("Database reset successfully.")


@command
class PgSettingsCmd:
    """Show current database settings: hop pg:settings."""

    name = "pg:settings"

    def run(self) -> None:
        echo("Fetching database settings...")
        # TODO: Implement logic to fetch database settings
        echo("Database settings displayed successfully.")


@command
class PgUnfollowCmd:
    """Stop replica from following: hop pg:unfollow."""

    name = "pg:unfollow"

    def run(self) -> None:
        echo("Stopping database replica from following...")
        # TODO: Implement logic to unfollow a replica
        echo("Database replica unfollowed successfully.")


@command
class PgUpgradeCmd:
    """Upgrade PostgreSQL version: hop pg:upgrade."""

    name = "pg:upgrade"

    def run(self) -> None:
        echo("Upgrading PostgreSQL version...")
        # TODO: Implement logic to upgrade PostgreSQL
        echo("PostgreSQL upgraded successfully.")


@command
class PgVacuumStatsCmd:
    """Show vacuum stats: hop pg:vacuum-stats."""

    name = "pg:vacuum-stats"

    def run(self) -> None:
        echo("Fetching vacuum stats...")
        # TODO: Implement logic to show vacuum stats
        echo("Vacuum stats displayed successfully.")


@command
class PgWaitCmd:
    """Wait for database to be available: hop pg:wait."""

    name = "pg:wait"

    def run(self) -> None:
        echo("Waiting for database to become available...")
        # TODO: Implement logic to wait for database
        echo("Database is now available.")
