# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Commands for managing backing services (databases, caches, etc.)."""

from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import TYPE_CHECKING

from hop3.core.credentials import get_credential_encryptor
from hop3.core.plugins import get_addon
from hop3.lib.decorators import register
from hop3.orm import EnvVar, ServiceCredential

from ._base import Command

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@register
@dataclass(frozen=True)
class ServicesCreateCmd(Command):
    """Create a new backing service instance.

    Usage: hop3 services:create <service-type> <service-name>

    Examples:
        hop3 services:create postgres my-database
        hop3 services:create redis my-cache
    """

    db_session: Session
    name = "services:create"

    def call(self, *args):
        """Create a new service instance."""
        if len(args) < 2:
            return [
                {
                    "t": "text",
                    "text": (
                        "Usage: hop3 services:create <service-type> <service-name>\n\n"
                        "Example:\n"
                        "  hop3 services:create postgres my-database"
                    ),
                }
            ]

        service_type = args[0]
        service_name = args[1]

        try:
            # Get the service strategy from the plugin system
            service = get_addon(service_type, service_name)

            # Create the service
            service.create()

            return [
                {
                    "t": "text",
                    "text": f"Service '{service_name}' of type '{service_type}' created successfully.",
                },
                {
                    "t": "text",
                    "text": f"\nTo attach this service to an app, run:\n  hop3 services:attach {service_name} --app <app-name>",
                },
            ]

        except RuntimeError as e:
            return [{"t": "error", "text": f"Error creating service: {e}"}]
        except Exception as e:
            return [{"t": "error", "text": f"Unexpected error: {e}"}]


@register
@dataclass(frozen=True)
class ServicesAttachCmd(Command):
    """Attach a service to an application.

    This command injects the service's connection details as environment
    variables into the specified application.

    Usage: hop3 services:attach <service-name> --app <app-name> [--service-type <type>]

    Examples:
        hop3 services:attach my-database --app my-app --service-type postgres
        hop3 services:attach my-cache --app my-app --service-type redis
    """

    db_session: Session
    name = "services:attach"

    def call(self, *args):
        """Attach a service to an application."""
        # Parse arguments
        if len(args) < 1:
            return [
                {
                    "t": "text",
                    "text": (
                        "Usage: hop3 services:attach <service-name> --app <app-name> [--service-type <type>]\n\n"
                        "Example:\n"
                        "  hop3 services:attach my-database --app my-app --service-type postgres"
                    ),
                }
            ]

        service_name = args[0]
        app_name = None
        service_type = "postgres"  # Default to postgres for now

        # Parse optional arguments
        i = 1
        while i < len(args):
            if args[i] == "--app" and i + 1 < len(args):
                app_name = args[i + 1]
                i += 2
            elif args[i] == "--service-type" and i + 1 < len(args):
                service_type = args[i + 1]
                i += 2
            else:
                i += 1

        if not app_name:
            return [
                {
                    "t": "error",
                    "text": "Error: --app parameter is required\n\nUsage: hop3 services:attach <service-name> --app <app-name>",
                }
            ]

        try:
            # Check if app exists
            from hop3.orm.repositories import AppRepository  # noqa: PLC0415

            app_repo = AppRepository(session=self.db_session)
            app = app_repo.get_one_or_none(name=app_name)

            if not app:
                return [{"t": "error", "text": f"App '{app_name}' not found"}]

            # Get the service strategy
            service = get_addon(service_type, service_name)

            # Get connection details from the service
            connection_details = service.get_connection_details()

            # Store credentials encrypted in database
            encryptor = get_credential_encryptor()

            # Check if credential already exists
            existing_credential = (
                self.db_session.query(ServiceCredential)
                .filter_by(
                    app_id=app.id, service_type=service_type, service_name=service_name
                )
                .first()
            )

            if existing_credential:
                # Update existing credential
                existing_credential.encrypted_data = encryptor.encrypt(
                    connection_details
                )
            else:
                # Create new credential
                credential = ServiceCredential(
                    app_id=app.id,
                    service_type=service_type,
                    service_name=service_name,
                    encrypted_data=encryptor.encrypt(connection_details),
                )
                self.db_session.add(credential)

            # Add each environment variable to the app
            added_vars = []
            for key, value in connection_details.items():
                # Check if variable already exists
                existing_var = (
                    self.db_session.query(EnvVar)
                    .filter_by(app_id=app.id, name=key)
                    .first()
                )

                if existing_var:
                    # Update existing variable
                    existing_var.value = value
                    added_vars.append(f"Updated {key}")
                else:
                    # Create new variable
                    env_var = EnvVar(app_id=app.id, name=key, value=value)
                    self.db_session.add(env_var)
                    added_vars.append(f"Added {key}")

            self.db_session.commit()

            return [
                {
                    "t": "text",
                    "text": f"Service '{service_name}' attached to app '{app_name}' successfully.",
                },
                {
                    "t": "text",
                    "text": "\nEnvironment variables:\n  " + "\n  ".join(added_vars),
                },
                {
                    "t": "text",
                    "text": f"\nRestart your app for changes to take effect:\n  hop3 restart {app_name}",
                },
            ]

        except RuntimeError as e:
            return [{"t": "error", "text": f"Error attaching service: {e}"}]
        except Exception as e:
            traceback.print_exc()
            return [{"t": "error", "text": f"Unexpected error: {e}"}]


@register
@dataclass(frozen=True)
class ServicesDetachCmd(Command):
    """Detach a service from an application.

    This removes the service's environment variables from the application.

    Usage: hop3 services:detach <service-name> --app <app-name> [--service-type <type>]
    """

    db_session: Session
    name = "services:detach"

    def call(self, *args):
        """Detach a service from an application."""
        if len(args) < 1:
            return [
                {
                    "t": "text",
                    "text": (
                        "Usage: hop3 services:detach <service-name> --app <app-name> [--service-type <type>]\n\n"
                        "Example:\n"
                        "  hop3 services:detach my-database --app my-app"
                    ),
                }
            ]

        service_name = args[0]
        app_name = None
        service_type = "postgres"  # Default

        # Parse optional arguments
        i = 1
        while i < len(args):
            if args[i] == "--app" and i + 1 < len(args):
                app_name = args[i + 1]
                i += 2
            elif args[i] == "--service-type" and i + 1 < len(args):
                service_type = args[i + 1]
                i += 2
            else:
                i += 1

        if not app_name:
            return [
                {
                    "t": "error",
                    "text": "Error: --app parameter is required",
                }
            ]

        try:
            # Check if app exists
            from hop3.orm.repositories import AppRepository  # noqa: PLC0415

            app_repo = AppRepository(session=self.db_session)
            app = app_repo.get_one_or_none(name=app_name)

            if not app:
                return [{"t": "error", "text": f"App '{app_name}' not found"}]

            # Remove stored credential
            credential = (
                self.db_session.query(ServiceCredential)
                .filter_by(
                    app_id=app.id, service_type=service_type, service_name=service_name
                )
                .first()
            )

            if credential:
                # Get connection details to know which env vars to remove
                encryptor = get_credential_encryptor()
                connection_details = encryptor.decrypt(credential.encrypted_data)

                # Remove the credential
                self.db_session.delete(credential)
            else:
                # Fallback: Try to get connection details from service if credential not found
                try:
                    service = get_addon(service_type, service_name)
                    connection_details = service.get_connection_details()
                except Exception:
                    # If we can't get connection details, we can't know which env vars to remove
                    connection_details = {}

            # Remove each environment variable
            removed_vars = []
            for key in connection_details:
                env_var = (
                    self.db_session.query(EnvVar)
                    .filter_by(app_id=app.id, name=key)
                    .first()
                )

                if env_var:
                    self.db_session.delete(env_var)
                    removed_vars.append(key)

            self.db_session.commit()

            if removed_vars:
                return [
                    {
                        "t": "text",
                        "text": f"Service '{service_name}' detached from app '{app_name}'.",
                    },
                    {"t": "text", "text": f"\nRemoved: {', '.join(removed_vars)}"},
                ]
            return [
                {
                    "t": "text",
                    "text": f"Service '{service_name}' was not attached to app '{app_name}'.",
                }
            ]

        except Exception as e:
            return [{"t": "error", "text": f"Error detaching service: {e}"}]


@register
@dataclass(frozen=True)
class ServicesDestroyCmd(Command):
    """Destroy a service instance.

    WARNING: This will permanently delete all data in the service!

    Usage: hop3 services:destroy <service-name> [--service-type <type>]
    """

    db_session: Session
    name = "services:destroy"
    destructive = True

    def call(self, *args):
        """Destroy a service instance."""
        if len(args) < 1:
            return [
                {
                    "t": "text",
                    "text": (
                        "Usage: hop3 services:destroy <service-name> [--service-type <type>]\n\n"
                        "WARNING: This will permanently delete all data!\n\n"
                        "Example:\n"
                        "  hop3 services:destroy my-database --service-type postgres"
                    ),
                }
            ]

        service_name = args[0]
        service_type = "postgres"  # Default

        # Parse optional arguments
        i = 1
        while i < len(args):
            if args[i] == "--service-type" and i + 1 < len(args):
                service_type = args[i + 1]
                i += 2
            else:
                i += 1

        try:
            # Get the service strategy
            service = get_addon(service_type, service_name)

            # Clean up all stored credentials for this service
            credentials = (
                self.db_session.query(ServiceCredential)
                .filter_by(service_type=service_type, service_name=service_name)
                .all()
            )

            for credential in credentials:
                self.db_session.delete(credential)

            self.db_session.commit()

            # Destroy the service
            service.destroy()

            return [
                {
                    "t": "text",
                    "text": f"Service '{service_name}' of type '{service_type}' destroyed successfully.",
                }
            ]

        except RuntimeError as e:
            return [{"t": "error", "text": f"Error destroying service: {e}"}]
        except Exception as e:
            return [{"t": "error", "text": f"Unexpected error: {e}"}]


@register
@dataclass(frozen=True)
class ServicesInfoCmd(Command):
    """Get information about a service instance.

    Usage: hop3 services:info <service-name> [--service-type <type>]
    """

    db_session: Session
    name = "services:info"

    def call(self, *args):
        """Get service information."""
        if len(args) < 1:
            return [
                {
                    "t": "text",
                    "text": (
                        "Usage: hop3 services:info <service-name> [--service-type <type>]\n\n"
                        "Example:\n"
                        "  hop3 services:info my-database --service-type postgres"
                    ),
                }
            ]

        service_name = args[0]
        service_type = "postgres"  # Default

        # Parse optional arguments
        i = 1
        while i < len(args):
            if args[i] == "--service-type" and i + 1 < len(args):
                service_type = args[i + 1]
                i += 2
            else:
                i += 1

        try:
            # Get the service strategy
            service = get_addon(service_type, service_name)

            # Get service info
            info = service.info()

            # Format the output
            lines = [f"Service: {service_name}", f"Type: {service_type}", ""]
            for key, value in info.items():
                if key not in {"service_name", "type"}:
                    lines.append(f"{key}: {value}")

            return [{"t": "text", "text": "\n".join(lines)}]

        except RuntimeError as e:
            return [{"t": "error", "text": f"Error getting service info: {e}"}]
        except Exception as e:
            return [{"t": "error", "text": f"Unexpected error: {e}"}]
