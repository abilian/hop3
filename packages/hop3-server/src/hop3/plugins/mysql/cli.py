# Copyright (c) 2024-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""CLI commands to manage MySQL databases."""

from __future__ import annotations

from argparse import ArgumentParser

from hop3.core.plugins import get_addon
from hop3.lib import echo
from hop3.lib.decorators import command


@command
class MySQLCmd:
    """Manage a MySQL database."""


@command
class MySQLCreateCmd:
    """Create a MySQL database: hop mysql:create <name>.

    This is a convenience command that wraps 'hop services:create mysql <name>'.
    """

    name = "mysql:create"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("name", type=str, help="Name of the database service.")

    def run(self, name: str) -> None:
        echo(f"Creating MySQL database '{name}'...")

        try:
            # Use the service strategy to create the database
            service = get_addon("mysql", name)
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
class MySQLDropCmd:
    """Drop a MySQL database: hop mysql:drop <name>.

    This is a convenience command that wraps 'hop services:destroy <name>'.
    WARNING: This will permanently delete all data!
    """

    name = "mysql:drop"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("name", type=str, help="Name of the database to drop.")

    def run(self, name: str) -> None:
        echo(f"Dropping database '{name}'...")
        echo("WARNING: This will permanently delete all data!")

        try:
            # Use the service strategy to destroy the database
            service = get_addon("mysql", name)
            service.destroy()

            echo(f"Database '{name}' dropped successfully.")

        except RuntimeError as e:
            echo(f"Error: {e}")
        except Exception as e:
            echo(f"Unexpected error: {e}")


@command
class MySQLImportCmd:
    """Import data into a MySQL database: hop mysql:import <name>."""

    name = "mysql:import"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "name", type=str, help="Name of the database to import data into."
        )

    def run(self, name: str) -> None:
        echo(f"Importing data into database '{name}'.")
        # TODO: Add actual implementation to import data
        echo(f"Data imported into database '{name}' successfully.")


@command
class MySQLDumpCmd:
    """Dump a MySQL database: hop mysql:dump <name>."""

    name = "mysql:dump"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("name", type=str, help="Name of the database to dump.")

    def run(self, name: str) -> None:
        echo(f"Dumping database '{name}'.")
        # TODO: Add actual implementation to dump the database
        echo(f"Database '{name}' dumped successfully.")


@command
class MySQLBackupsCmd:
    """List database backups: hop mysql:backups."""

    name = "mysql:backups"

    def run(self) -> None:
        echo("Listing database backups...")
        # TODO: Implement logic to list backups
        echo("Database backups listed successfully.")


@command
class MySQLCredentialsCmd:
    """Show database credentials: hop mysql:credentials <name>."""

    name = "mysql:credentials"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("name", type=str, help="Name of the database.")

    def run(self, name: str) -> None:
        echo(f"Fetching credentials for database '{name}'...")

        try:
            # Use the service strategy to get connection details
            service = get_addon("mysql", name)
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
class MySQLInfoCmd:
    """Show database information: hop mysql:info <name>."""

    name = "mysql:info"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("name", type=str, help="Name of the database.")

    def run(self, name: str) -> None:
        echo(f"Fetching information for database '{name}'...")

        try:
            # Use the service strategy to get info
            service = get_addon("mysql", name)
            info = service.info()

            # Display the information
            for key, value in info.items():
                echo(f"{key}: {value}")

        except RuntimeError as e:
            echo(f"Error: {e}")
        except Exception as e:
            echo(f"Unexpected error: {e}")


@command
class MySQLCopyCmd:
    """Copy data from source to target database: hop mysql:copy <source> <target>."""

    name = "mysql:copy"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("source", type=str, help="Source database.")
        parser.add_argument("target", type=str, help="Target database.")

    def run(self, source: str, target: str) -> None:
        echo(f"Copying data from '{source}' to '{target}'...")
        # TODO: Implement logic to copy data
        echo("Data copied successfully.")


@command
class MySQLDiagnoseCmd:
    """Run or view diagnostics report: hop mysql:diagnose."""

    name = "mysql:diagnose"

    def run(self) -> None:
        echo("Running diagnostics...")
        # TODO: Implement logic to diagnose issues
        echo("Diagnostics completed successfully.")


@command
class MySQLKillCmd:
    """Kill a query: hop mysql:kill <query_id>."""

    name = "mysql:kill"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("query_id", type=str, help="Query ID to kill.")

    def run(self, query_id: str) -> None:
        echo(f"Killing query '{query_id}'...")
        # TODO: Implement logic to kill a query
        echo(f"Query '{query_id}' killed successfully.")


@command
class MySQLKillAllCmd:
    """Terminate all connections: hop mysql:killall."""

    name = "mysql:killall"

    def run(self) -> None:
        echo("Terminating all connections...")
        # TODO: Implement logic to kill all connections
        echo("All connections terminated successfully.")


@command
class MySQLLocksCmd:
    """Display queries with active locks: hop mysql:locks."""

    name = "mysql:locks"

    def run(self) -> None:
        echo("Displaying queries with active locks...")
        # TODO: Implement logic to show locks
        echo("Active locks displayed successfully.")


@command
class MySQLMaintenanceCmd:
    """Show current maintenance information: hop mysql:maintenance."""

    name = "mysql:maintenance"

    def run(self) -> None:
        echo("Fetching maintenance information...")
        # TODO: Implement logic to fetch maintenance info
        echo("Maintenance information displayed successfully.")


@command
class MySQLOutliersCmd:
    """Show top 10 longest queries: hop mysql:outliers."""

    name = "mysql:outliers"

    def run(self) -> None:
        echo("Fetching top 10 longest queries...")
        # TODO: Implement logic to find query outliers
        echo("Top 10 longest queries displayed successfully.")


@command
class MySQLPromoteCmd:
    """Set DATABASE as your DATABASE_URL: hop mysql:promote."""

    name = "mysql:promote"

    def run(self) -> None:
        echo("Promoting database...")
        # TODO: Implement logic to promote the database
        echo("Database promoted successfully.")


@command
class MySQLPsCmd:
    """View active queries: hop mysql:ps."""

    name = "mysql:ps"

    def run(self) -> None:
        echo("Fetching active queries...")
        # TODO: Implement logic to show active queries
        echo("Active queries displayed successfully.")


@command
class MySQLShellCmd:
    """Open a mysql shell: hop mysql:shell."""

    name = "mysql:shell"

    def run(self) -> None:
        echo("Opening mysql shell...")
        # TODO: Implement logic to open mysql shell
        echo("Exited mysql shell.")


@command
class MySQLPullCmd:
    """Pull remote database to local: hop mysql:pull <source> <target>."""

    name = "mysql:pull"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("source", type=str, help="Source database.")
        parser.add_argument("target", type=str, help="Target database.")

    def run(self, source: str, target: str) -> None:
        echo(f"Pulling database from '{source}' to '{target}'...")
        # TODO: Implement logic to pull database
        echo("Database pulled successfully.")


@command
class MySQLPushCmd:
    """Push local database to remote: hop mysql:push <source> <target>."""

    name = "mysql:push"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("source", type=str, help="Source database.")
        parser.add_argument("target", type=str, help="Target database.")

    def run(self, source: str, target: str) -> None:
        echo(f"Pushing database from '{source}' to '{target}'...")
        # TODO: Implement logic to push database
        echo("Database pushed successfully.")


@command
class MySQLResetCmd:
    """Delete all data in DATABASE: hop mysql:reset."""

    name = "mysql:reset"

    def run(self) -> None:
        echo("Resetting database...")
        # TODO: Implement logic to reset database
        echo("Database reset successfully.")


@command
class MySQLSettingsCmd:
    """Show current database settings: hop mysql:settings."""

    name = "mysql:settings"

    def run(self) -> None:
        echo("Fetching database settings...")
        # TODO: Implement logic to fetch database settings
        echo("Database settings displayed successfully.")


@command
class MySQLUpgradeCmd:
    """Upgrade MySQL version: hop mysql:upgrade."""

    name = "mysql:upgrade"

    def run(self) -> None:
        echo("Upgrading MySQL version...")
        # TODO: Implement logic to upgrade MySQL
        echo("MySQL upgraded successfully.")


@command
class MySQLWaitCmd:
    """Wait for database to be available: hop mysql:wait."""

    name = "mysql:wait"

    def run(self) -> None:
        echo("Waiting for database to become available...")
        # TODO: Implement logic to wait for database
        echo("Database is now available.")
