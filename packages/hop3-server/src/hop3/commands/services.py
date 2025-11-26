# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Commands for managing backing services (databases, caches, etc.)."""

from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from hop3.core.credentials import get_credential_encryptor
from hop3.core.plugins import get_addon
from hop3.lib.decorators import register
from hop3.orm import AddonCredential, EnvVar

from ._base import Command

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@register
@dataclass(frozen=True)
class AddonsCreateCmd(Command):
    """Create a new backing service instance.

    Usage: hop3 addons:create <service-type> <service-name>

    Examples:
        hop3 addons:create postgres my-database
        hop3 addons:create redis my-cache
    """

    db_session: Session
    name: ClassVar[str] = "addons:create"

    def call(self, *args):
        """Create a new service instance."""
        if len(args) < 2:
            return [
                {
                    "t": "text",
                    "text": (
                        "Usage: hop3 addons:create <service-type> <service-name>\n\n"
                        "Example:\n"
                        "  hop3 addons:create postgres my-database"
                    ),
                }
            ]

        service_type = args[0]
        addon_name = args[1]

        try:
            # Get the service strategy from the plugin system
            addon = get_addon(service_type, addon_name)

            # Create the service
            addon.create()

            return [
                {
                    "t": "text",
                    "text": f"Addon '{addon_name}' of type '{service_type}' created successfully.",
                },
                {
                    "t": "text",
                    "text": f"\nTo attach this service to an app, run:\n  hop3 addons:attach {addon_name} --app <app-name>",
                },
            ]

        except RuntimeError as e:
            return [{"t": "error", "text": f"Error creating service: {e}"}]
        except Exception as e:
            return [{"t": "error", "text": f"Unexpected error: {e}"}]


@register
@dataclass(frozen=True)
class AddonsAttachCmd(Command):
    """Attach a service to an application.

    This command injects the service's connection details as environment
    variables into the specified application.

    Usage: hop3 addons:attach <service-name> --app <app-name> [--service-type <type>]

    Examples:
        hop3 addons:attach my-database --app my-app --service-type postgres
        hop3 addons:attach my-cache --app my-app --service-type redis
    """

    db_session: Session
    name: ClassVar[str] = "addons:attach"

    def _parse_attach_args(self, args) -> tuple[str, str | None, str] | None:
        """Parse command arguments.

        Returns:
            Tuple of (addon_name, app_name, service_type) or None if invalid
        """
        if len(args) < 1:
            return None

        addon_name = args[0]
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

        return addon_name, app_name, service_type

    def _store_or_update_credential(
        self,
        app_id: int,
        service_type: str,
        addon_name: str,
        connection_details: dict,
    ):
        """Store or update encrypted service credentials."""
        encryptor = get_credential_encryptor()

        existing_credential = (
            self.db_session.query(AddonCredential)
            .filter_by(app_id=app_id, addon_type=service_type, addon_name=addon_name)
            .first()
        )

        if existing_credential:
            existing_credential.encrypted_data = encryptor.encrypt(connection_details)
        else:
            credential = AddonCredential(
                app_id=app_id,
                addon_type=service_type,
                addon_name=addon_name,
                encrypted_data=encryptor.encrypt(connection_details),
            )
            self.db_session.add(credential)

    def _add_env_vars(self, app_id: int, connection_details: dict) -> list[str]:
        """Add or update environment variables for the app.

        Returns:
            List of status messages for each variable added/updated
        """
        added_vars = []
        for key, value in connection_details.items():
            existing_var = (
                self.db_session.query(EnvVar).filter_by(app_id=app_id, name=key).first()
            )

            if existing_var:
                existing_var.value = value
                added_vars.append(f"Updated {key}")
            else:
                env_var = EnvVar(app_id=app_id, name=key, value=value)
                self.db_session.add(env_var)
                added_vars.append(f"Added {key}")

        return added_vars

    def call(self, *args):
        """Attach a service to an application."""
        parsed = self._parse_attach_args(args)
        if not parsed:
            return [
                {
                    "t": "text",
                    "text": (
                        "Usage: hop3 addons:attach <service-name> --app <app-name> [--service-type <type>]\n\n"
                        "Example:\n"
                        "  hop3 addons:attach my-database --app my-app --service-type postgres"
                    ),
                }
            ]

        addon_name, app_name, service_type = parsed

        if not app_name:
            return [
                {
                    "t": "error",
                    "text": "Error: --app parameter is required\n\nUsage: hop3 addons:attach <service-name> --app <app-name>",
                }
            ]

        try:
            # Check if app exists
            from hop3.orm.repositories import AppRepository  # noqa: PLC0415

            app_repo = AppRepository(session=self.db_session)
            app = app_repo.get_one_or_none(name=app_name)

            if not app:
                return [{"t": "error", "text": f"App '{app_name}' not found"}]

            # Get the service strategy and connection details
            addon = get_addon(service_type, addon_name)
            connection_details = addon.get_connection_details()

            # Store credentials and add environment variables
            self._store_or_update_credential(
                app.id, service_type, addon_name, connection_details
            )
            added_vars = self._add_env_vars(app.id, connection_details)

            self.db_session.commit()

            return [
                {
                    "t": "text",
                    "text": f"Addon '{addon_name}' attached to app '{app_name}' successfully.",
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
class AddonsDetachCmd(Command):
    """Detach a service from an application.

    This removes the service's environment variables from the application.

    Usage: hop3 addons:detach <service-name> --app <app-name> [--service-type <type>]
    """

    db_session: Session
    name: ClassVar[str] = "addons:detach"

    def _parse_detach_args(self, args) -> tuple[str, str | None, str] | None:
        """Parse command arguments.

        Returns:
            Tuple of (addon_name, app_name, service_type) or None if invalid
        """
        if len(args) < 1:
            return None

        addon_name = args[0]
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

        return addon_name, app_name, service_type

    def _get_connection_details(
        self, app_id: int, service_type: str, addon_name: str
    ) -> dict:
        """Get connection details from stored credential or service.

        Returns:
            Dictionary of connection details (may be empty if not found)
        """
        credential = (
            self.db_session.query(AddonCredential)
            .filter_by(app_id=app_id, addon_type=service_type, addon_name=addon_name)
            .first()
        )

        if credential:
            encryptor = get_credential_encryptor()
            connection_details = encryptor.decrypt(credential.encrypted_data)
            # Remove the credential
            self.db_session.delete(credential)
            return connection_details

        # Fallback: Try to get connection details from service
        try:
            addon = get_addon(service_type, addon_name)
            return addon.get_connection_details()
        except Exception:
            # If we can't get connection details, return empty dict
            return {}

    def _remove_env_vars(self, app_id: int, connection_details: dict) -> list[str]:
        """Remove environment variables from the app.

        Returns:
            List of removed variable names
        """
        removed_vars = []
        for key in connection_details:
            env_var = (
                self.db_session.query(EnvVar).filter_by(app_id=app_id, name=key).first()
            )

            if env_var:
                self.db_session.delete(env_var)
                removed_vars.append(key)

        return removed_vars

    def call(self, *args):
        """Detach a service from an application."""
        parsed = self._parse_detach_args(args)
        if not parsed:
            return [
                {
                    "t": "text",
                    "text": (
                        "Usage: hop3 addons:detach <service-name> --app <app-name> [--service-type <type>]\n\n"
                        "Example:\n"
                        "  hop3 addons:detach my-database --app my-app"
                    ),
                }
            ]

        addon_name, app_name, service_type = parsed

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

            # Get connection details and remove credential
            connection_details = self._get_connection_details(
                app.id, service_type, addon_name
            )

            # Remove environment variables
            removed_vars = self._remove_env_vars(app.id, connection_details)

            self.db_session.commit()

            if removed_vars:
                return [
                    {
                        "t": "text",
                        "text": f"Addon '{addon_name}' detached from app '{app_name}'.",
                    },
                    {"t": "text", "text": f"\nRemoved: {', '.join(removed_vars)}"},
                ]
            return [
                {
                    "t": "text",
                    "text": f"Addon '{addon_name}' was not attached to app '{app_name}'.",
                }
            ]

        except Exception as e:
            return [{"t": "error", "text": f"Error detaching service: {e}"}]


@register
@dataclass(frozen=True)
class AddonsDestroyCmd(Command):
    """Destroy a service instance.

    WARNING: This will permanently delete all data in the service!

    Usage: hop3 addons:destroy <service-name> [--service-type <type>]
    """

    db_session: Session
    name: ClassVar[str] = "addons:destroy"
    destructive: ClassVar[bool] = True

    def call(self, *args):
        """Destroy a service instance."""
        if len(args) < 1:
            return [
                {
                    "t": "text",
                    "text": (
                        "Usage: hop3 addons:destroy <service-name> [--service-type <type>]\n\n"
                        "WARNING: This will permanently delete all data!\n\n"
                        "Example:\n"
                        "  hop3 addons:destroy my-database --service-type postgres"
                    ),
                }
            ]

        addon_name = args[0]
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
            addon = get_addon(service_type, addon_name)

            # Clean up all stored credentials for this service
            credentials = (
                self.db_session.query(AddonCredential)
                .filter_by(addon_type=service_type, addon_name=addon_name)
                .all()
            )

            for credential in credentials:
                self.db_session.delete(credential)

            self.db_session.commit()

            # Destroy the service
            addon.destroy()

            return [
                {
                    "t": "text",
                    "text": f"Addon '{addon_name}' of type '{service_type}' destroyed successfully.",
                }
            ]

        except RuntimeError as e:
            return [{"t": "error", "text": f"Error destroying service: {e}"}]
        except Exception as e:
            return [{"t": "error", "text": f"Unexpected error: {e}"}]


@register
@dataclass(frozen=True)
class AddonsInfoCmd(Command):
    """Get information about a service instance.

    Usage: hop3 addons:info <service-name> [--service-type <type>]
    """

    db_session: Session
    name: ClassVar[str] = "addons:info"

    def call(self, *args):
        """Get service information."""
        if len(args) < 1:
            return [
                {
                    "t": "text",
                    "text": (
                        "Usage: hop3 addons:info <service-name> [--service-type <type>]\n\n"
                        "Example:\n"
                        "  hop3 addons:info my-database --service-type postgres"
                    ),
                }
            ]

        addon_name = args[0]
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
            addon = get_addon(service_type, addon_name)

            # Get service info
            info = addon.info()

            # Format the output
            lines = [f"Addon: {addon_name}", f"Type: {service_type}", ""]
            for key, value in info.items():
                if key not in {"addon_name", "type"}:
                    lines.append(f"{key}: {value}")

            return [{"t": "text", "text": "\n".join(lines)}]

        except RuntimeError as e:
            return [{"t": "error", "text": f"Error getting service info: {e}"}]
        except Exception as e:
            return [{"t": "error", "text": f"Unexpected error: {e}"}]
