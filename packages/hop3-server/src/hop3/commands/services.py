# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Commands for managing backing services (databases, caches, etc.)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from hop3.core.credentials import get_credential_encryptor
from hop3.core.plugins import get_addon, get_plugin_manager
from hop3.lib.decorators import register
from hop3.lib.logging import server_log
from hop3.orm import AddonCredential, EnvVar

from ._base import Command
from ._errors import command_context

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@register
@dataclass(frozen=True)
class AddonsListCmd(Command):
    """List available addon types.

    Usage: hop3 addons:list

    Shows all registered addon types that can be created.
    """

    db_session: Session
    name: ClassVar[str] = "addons:list"

    def call(self, *args):
        """List available addon types."""
        server_log.info("addons:list called")

        pm = get_plugin_manager()
        addon_classes_list = pm.hook.get_addons()
        addon_classes = [cls for sublist in addon_classes_list for cls in sublist]

        server_log.info(
            "addons:list found addons",
            count=len(addon_classes),
            addon_types=[getattr(cls, "name", "?") for cls in addon_classes],
        )

        if not addon_classes:
            return [
                {"t": "warning", "text": "No addon types registered."},
                {
                    "t": "text",
                    "text": "Check that addon plugins are properly installed.",
                },
            ]

        rows = []
        for addon_class in addon_classes:
            addon_name = getattr(addon_class, "name", "unknown")
            addon_module = addon_class.__module__
            rows.append([addon_name, addon_module])

        return [
            {"t": "text", "text": "Available addon types:"},
            {
                "t": "table",
                "headers": ["Type", "Module"],
                "rows": rows,
            },
        ]


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
        server_log.info("addons:create called", args=args)

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

        with command_context(
            "creating addon", addon_name=addon_name, service_type=service_type
        ):
            # Get the service strategy from the plugin system
            server_log.info(
                "addons:create getting addon",
                service_type=service_type,
                addon_name=addon_name,
            )
            addon = get_addon(service_type, addon_name)

            # Create the service
            server_log.info("addons:create calling addon.create()")
            addon.create()
            server_log.info("addons:create addon.create() completed successfully")

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
            self.db_session
            .query(AddonCredential)
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

    def _add_env_vars(self, app, connection_details: dict) -> list[str]:
        """Add or update environment variables for the app.

        Uses the same pattern as config:set - using the relationship and
        appending to app.env_vars to ensure SQLAlchemy properly tracks changes.

        Args:
            app: The App ORM object (not just app_id)
            connection_details: Dict of env var name -> value

        Returns:
            List of status messages for each variable added/updated
        """
        server_log.info(
            "Adding env vars from addon",
            app_id=app.id,
            app_name=app.name,
            connection_details_keys=list(connection_details.keys()),
            current_env_vars=[ev.name for ev in app.env_vars],
        )

        added_vars = []
        for key, value in connection_details.items():
            # Truncate value for logging (don't log full URLs with passwords)
            log_value = value[:30] + "..." if len(str(value)) > 30 else value
            server_log.debug(
                "Processing env var",
                app_id=app.id,
                key=key,
                value_preview=log_value,
            )

            # Check if variable already exists (same pattern as config:set)
            existing = None
            for env_var in app.env_vars:
                if env_var.name == key:
                    existing = env_var
                    break

            if existing:
                existing.value = value
                added_vars.append(f"Updated {key}")
                server_log.info("Updated existing env var", app_id=app.id, key=key)
            else:
                # Create EnvVar with app_id and add to session
                # Then append to app.env_vars for immediate visibility
                # This pattern works with both real SQLAlchemy apps and mocks
                new_var = EnvVar(app_id=app.id, name=key, value=value)
                self.db_session.add(new_var)
                # Also append to collection for immediate visibility
                # (this is what config:set does via relationship assignment)
                app.env_vars.append(new_var)
                added_vars.append(f"Added {key}")
                server_log.info("Added new env var", app_id=app.id, key=key)

        server_log.info(
            "Env vars processing complete",
            app_id=app.id,
            added_vars=added_vars,
            total_env_vars=[ev.name for ev in app.env_vars],
        )
        return added_vars

    def call(self, *args):
        """Attach a service to an application."""
        server_log.info("addons:attach called", args=args)

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
        server_log.info(
            "addons:attach parsed args",
            addon_name=addon_name,
            app_name=app_name,
            service_type=service_type,
        )

        if not app_name:
            return [
                {
                    "t": "error",
                    "text": "Error: --app parameter is required\n\nUsage: hop3 addons:attach <service-name> --app <app-name>",
                }
            ]

        with command_context(
            "attaching addon", addon_name=addon_name, app_name=app_name
        ):
            # Check if app exists
            from hop3.orm.repositories import AppRepository  # noqa: PLC0415

            app_repo = AppRepository(session=self.db_session)
            app = app_repo.get_one_or_none(name=app_name)

            if not app:
                server_log.warning("addons:attach app not found", app_name=app_name)
                msg = f"App '{app_name}' not found"
                raise ValueError(msg)

            server_log.info(
                "addons:attach found app",
                app_name=app_name,
                app_id=app.id,
                current_env_vars_count=len(list(app.env_vars)),
            )

            # Get the service strategy and connection details
            addon = get_addon(service_type, addon_name)
            server_log.info(
                "addons:attach got addon",
                addon_type=type(addon).__name__,
                addon_name=addon_name,
            )

            # Get connection details - this may raise RuntimeError if password not found
            connection_details = addon.get_connection_details()

            server_log.info(
                "addons:attach got connection details",
                connection_details_keys=list(connection_details.keys()),
                has_database_url="DATABASE_URL" in connection_details,
            )

            if not connection_details:
                server_log.error("addons:attach connection_details is empty!")
                msg = "No connection details returned from addon"
                raise ValueError(msg)

            # Store credentials and add environment variables
            self._store_or_update_credential(
                app.id, service_type, addon_name, connection_details
            )
            # Pass the app object (not just app.id) to properly track relationships
            added_vars = self._add_env_vars(app, connection_details)

            self.db_session.commit()
            server_log.info(
                "addons:attach committed",
                app_id=app.id,
                added_vars=added_vars,
            )

            # Expire all objects to ensure fresh data is loaded for verification
            self.db_session.expire_all()

            # Verify env vars were stored by loading app fresh
            app_repo2 = AppRepository(session=self.db_session)
            app_after = app_repo2.get_one_or_none(name=app_name)
            if app_after:
                env_var_names = [ev.name for ev in app_after.env_vars]
                server_log.info(
                    "addons:attach verification",
                    app_id=app_after.id,
                    env_vars_count_after=len(env_var_names),
                    env_vars_names=env_var_names,
                )
                # Also verify in the returned message
                if "DATABASE_URL" not in env_var_names:
                    server_log.warning(
                        "DATABASE_URL not found in app env vars after commit!",
                        app_id=app_after.id,
                        env_var_names=env_var_names,
                    )

        # Build response with details about what was added
        response = [
            {
                "t": "text",
                "text": f"Addon '{addon_name}' attached to app '{app_name}' successfully.",
            },
        ]

        if added_vars:
            response.append({
                "t": "text",
                "text": "\nEnvironment variables:\n  " + "\n  ".join(added_vars),
            })
        else:
            response.append({
                "t": "warning",
                "text": "\nWARNING: No environment variables were added!",
            })

        response.append({
            "t": "text",
            "text": f"\nRedeploy your app for changes to take effect:\n  hop3 deploy {app_name}",
        })

        return response


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
            self.db_session
            .query(AddonCredential)
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

        with command_context(
            "detaching addon", addon_name=addon_name, app_name=app_name
        ):
            # Check if app exists
            from hop3.orm.repositories import AppRepository  # noqa: PLC0415

            app_repo = AppRepository(session=self.db_session)
            app = app_repo.get_one_or_none(name=app_name)

            if not app:
                msg = f"App '{app_name}' not found"
                raise ValueError(msg)

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

        with command_context(
            "destroying addon", addon_name=addon_name, service_type=service_type
        ):
            # Get the service strategy
            addon = get_addon(service_type, addon_name)

            # Clean up all stored credentials for this service
            credentials = (
                self.db_session
                .query(AddonCredential)
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

        with command_context(
            "getting addon info", addon_name=addon_name, service_type=service_type
        ):
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


@register
@dataclass(frozen=True)
class AddonsStatusCmd(Command):
    """Show detailed status and health of an addon.

    Performs a health check on the addon and shows all attached applications.

    Usage: hop3 addons:status <service-name> [--service-type <type>]

    Examples:
        hop3 addons:status my-database --service-type postgres
        hop3 addons:status my-cache --service-type redis
    """

    db_session: Session
    name: ClassVar[str] = "addons:status"

    def call(self, *args):
        """Get detailed addon status with health check."""
        if len(args) < 1:
            return self._usage_message()

        addon_name, service_type = self._parse_args(args)

        with command_context(
            "getting addon status", addon_name=addon_name, service_type=service_type
        ):
            addon = get_addon(service_type, addon_name)
            health_status, health_error = self._check_addon_health(addon)
            attached_apps = self._get_attached_apps(service_type, addon_name)
            rows = self._build_status_rows(
                addon,
                addon_name,
                service_type,
                health_status,
                health_error,
                attached_apps,
            )

        return [{"t": "table", "headers": ["Property", "Value"], "rows": rows}]

    def _usage_message(self) -> list[dict]:
        """Return usage message."""
        return [
            {
                "t": "text",
                "text": (
                    "Usage: hop3 addons:status <service-name> [--service-type <type>]\n\n"
                    "Example:\n"
                    "  hop3 addons:status my-database --service-type postgres"
                ),
            }
        ]

    def _parse_args(self, args: tuple) -> tuple[str, str]:
        """Parse command arguments."""
        addon_name = args[0]
        service_type = "postgres"  # Default

        i = 1
        while i < len(args):
            if args[i] == "--service-type" and i + 1 < len(args):
                service_type = args[i + 1]
                i += 2
            else:
                i += 1

        return addon_name, service_type

    def _check_addon_health(self, addon) -> tuple[str, str | None]:
        """Perform health check on addon."""
        health_status = "Unknown"
        health_error = None
        try:
            if hasattr(addon, "health_check"):
                healthy = addon.health_check()
                health_status = "Healthy" if healthy else "Unhealthy"
            elif hasattr(addon, "info"):
                addon.info()
                health_status = "Available"
        except Exception as e:
            health_status = "Unhealthy"
            health_error = str(e)
        return health_status, health_error

    def _get_attached_apps(self, service_type: str, addon_name: str) -> list[str]:
        """Get list of apps attached to this addon."""
        credentials = (
            self.db_session
            .query(AddonCredential)
            .filter_by(addon_type=service_type, addon_name=addon_name)
            .all()
        )
        return [cred.app.name for cred in credentials if cred.app]

    def _build_status_rows(
        self,
        addon,
        addon_name: str,
        service_type: str,
        health_status: str,
        health_error: str | None,
        attached_apps: list[str],
    ) -> list[list[str]]:
        """Build output rows for status table."""
        rows = [
            ["Name", addon_name],
            ["Type", service_type],
            ["Status", health_status],
            ["Attached Apps", ", ".join(attached_apps) if attached_apps else "None"],
        ]

        if health_error:
            rows.append(["Error", health_error])

        # Try to get additional info
        try:
            info = addon.info()
            for key in ("host", "port", "version"):
                if key in info:
                    rows.append([key.capitalize(), str(info[key])])
        except Exception:
            pass

        return rows
