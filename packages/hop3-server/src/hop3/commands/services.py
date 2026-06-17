# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Commands for managing backing services (databases, caches, etc.)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar
from urllib.parse import urlparse

from hop3.config import config
from hop3.core.credentials import get_credential_encryptor
from hop3.core.identifiers import InvalidIdentifierError, validate_service_name
from hop3.core.plugins import get_addon, get_plugin_manager
from hop3.deployers.addon_provisioning import (
    addon_var_prefix,
    sync_addon_env_vars,
)
from hop3.deployers.expose import connection_url, expose_addon, unexpose_addon
from hop3.lib.args import parse_cli_args
from hop3.lib.decorators import register
from hop3.lib.logging import server_log
from hop3.orm import AddonCredential

# Runtime imports for Dishka DI (not just type hints)
from hop3.orm.repositories import (  # noqa: TC001
    AddonCredentialRepository,
    AppRepository,
    EnvVarRepository,
    PortClaimRepository,
)
from hop3.plugins.addons.secrets import list_addon_instances

from ._base import Command
from ._errors import command_context
from ._response import data, error, summary, table, text, warning


@register
@dataclass(frozen=True)
class AddonsCmd(Command):
    """Manage backing services (databases, caches, etc.).

    Examples:
        hop3 addon list                   # List backing service instances (alias: 'hop3 addons')
        hop3 addon list --app my-app      # List addons attached to an app
        hop3 addon create postgres mydb   # Provision a new Postgres addon
        hop3 addon types                  # List available addon types
    """

    name: ClassVar[tuple[str, ...]] = ("addon",)


@register
@dataclass(frozen=True)
class AddonListCmd(Command):
    """List addon instances.

    Lists the backing-service instances provisioned on this server. Use
    --app to list only the addons attached to a given application, or
    --type to filter by addon type.

    To list the addon *types* that can be created, use 'hop3 addon types'.

    Usage: hop3 addon list [--app <app>] [--type <type>]

    Examples:
        hop3 addon list                   # All instances on the server
        hop3 addons                       # Same via alias
        hop3 addon list --app my-app      # Addons attached to my-app
        hop3 addon list --type postgres   # Only Postgres instances
    """

    app_repo: AppRepository
    addon_credential_repo: AddonCredentialRepository
    name: ClassVar[tuple[str, ...]] = ("addon", "list")
    requires_auth: ClassVar[bool] = True
    _arg_spec: ClassVar[dict] = {
        "app": {"type": str},  # --app <name>
        "type": {"type": str},  # --type <type>
    }

    def call(self, *args):
        """List addon instances, optionally scoped to an app or type."""
        parsed = parse_cli_args(args, self._arg_spec)
        app_name = parsed.get("app")
        type_filter = parsed.get("type")
        server_log.info("addon list called", app=app_name, type=type_filter)

        if app_name:
            return self._list_for_app(app_name, type_filter)
        return self._list_all(type_filter)

    def _list_all(self, type_filter: str | None):
        """List every instance on the server, with its attached apps."""
        instances = list_addon_instances()
        if type_filter:
            instances = [(t, n) for t, n in instances if t == type_filter]

        if not instances:
            if type_filter:
                return [text(f"No addon instances of type '{type_filter}'.")]
            return [
                text("No addon instances."),
                text("Create one with: hop3 addon create <type> <name>"),
            ]

        # Map (addon_type, addon_name) -> [app names] from the attachment table.
        attachments: dict[tuple[str, str], list[str]] = {}
        for cred in self.addon_credential_repo.list_all_with_apps():
            if cred.app:
                key = (cred.addon_type, cred.addon_name)
                attachments.setdefault(key, []).append(cred.app.name)

        rows = []
        for addon_type, addon_name in instances:
            apps = attachments.get((addon_type, addon_name), [])
            rows.append([addon_name, addon_type, ", ".join(apps) if apps else "-"])

        return [table(headers=["Name", "Type", "Attached apps"], rows=rows)]

    def _list_for_app(self, app_name: str, type_filter: str | None):
        """List the addons attached to a single app."""
        app = self.app_repo.get_one_or_none(name=app_name)
        if not app:
            return [error(f"App '{app_name}' not found")]

        creds = list(app.addon_credentials)
        if type_filter:
            creds = [c for c in creds if c.addon_type == type_filter]

        if not creds:
            return [text(f"No addons attached to app '{app_name}'.")]

        rows = [[c.addon_name, c.addon_type] for c in creds]
        return [
            text(f"Addons attached to '{app_name}':"),
            table(headers=["Name", "Type"], rows=rows),
        ]


def _resolve_addon_types(addon_name: str) -> list[str]:
    """Return the type(s) of the provisioned addon instance(s) named `addon_name`.

    A name *could* collide across types (a postgres and a redis both named
    "cache"); the caller disambiguates rather than guessing.
    """
    return [t for t, n in list_addon_instances() if n == addon_name]


def _resolve_one_type(addon_name: str, explicit: str | None) -> tuple[str | None, list]:
    """Resolve a single addon type for a type-agnostic command.

    Returns ``(addon_type, error_items)``. When ``error_items`` is non-empty the
    caller returns them as-is (unknown name, or ambiguous across types and no
    explicit ``--type`` given).
    """
    if explicit:
        return explicit, []
    types = _resolve_addon_types(addon_name)
    if not types:
        return None, [error(f"No addon named '{addon_name}'.")]
    if len(types) > 1:
        joined = ", ".join(sorted(types))
        return None, [
            error(
                f"Addon name '{addon_name}' is ambiguous (types: {joined}). "
                "Pass --type <type>."
            )
        ]
    return types[0], []


@register
@dataclass(frozen=True)
class AddonEndpointCmd(Command):
    """Show an addon's connection endpoint (type-agnostic).

    Usage: hop3 addon endpoint <name>

    The addon's type is resolved from its name, so no `--type` is needed.
    Prints the connection URL plus host/port. `hop3 tunnel` uses this; it is
    also handy on its own.

    Examples:
        hop3 addon endpoint mydb
    """

    name: ClassVar[tuple[str, ...]] = ("addon", "endpoint")
    requires_auth: ClassVar[bool] = True

    def call(self, *args):
        if not args:
            return [text("Usage: hop3 addon endpoint <name>")]
        addon_name = args[0]
        types = _resolve_addon_types(addon_name)
        if not types:
            return [error(f"No addon named '{addon_name}'.")]
        if len(types) > 1:
            joined = ", ".join(sorted(types))
            return [
                error(
                    f"Addon name '{addon_name}' is ambiguous (types: {joined}). "
                    "Rename one of them; addon names must be unique to tunnel."
                )
            ]
        addon_type = types[0]
        with command_context(
            "reading addon endpoint", addon_name=addon_name, service_type=addon_type
        ):
            details = get_addon(addon_type, addon_name).get_connection_details()
        url = connection_url(details)
        if url is None:
            return [error(f"Addon '{addon_name}' exposes no connection URL.")]
        parsed = urlparse(url)
        payload = {
            "type": addon_type,
            "host": parsed.hostname,
            "port": parsed.port,
            "url": url,
        }
        return [
            data(payload),
            table(
                headers=["Field", "Value"],
                rows=[
                    ["Type", addon_type],
                    ["Host", str(parsed.hostname)],
                    ["Port", str(parsed.port)],
                    ["URL", url],
                ],
            ),
        ]


@register
@dataclass(frozen=True)
class AddonExistsCmd(Command):
    """Predicate: does an addon exist? (type-agnostic, for scripts/CI).

    Usage: hop3 addon exists <name> [--type <type>]

    A predicate command: it prints nothing and exits 0 if the addon exists, 1
    if it doesn't (so it composes with shell `&&`/`||`). With `--json` it also
    prints `{"exists": true|false}`. Pass `--type` to require a specific type.

    Examples:
        hop3 addon exists mydb && hop3 addon promote mydb --app web
        hop3 addon exists mydb --type postgres
    """

    name: ClassVar[tuple[str, ...]] = ("addon", "exists")
    requires_auth: ClassVar[bool] = True
    _arg_spec: ClassVar[dict] = {
        "addon_name": {"positional": True},
        "type": {"type": str},
        "service_type": {"type": str},
    }

    def call(self, *args):
        parsed = parse_cli_args(args, self._arg_spec)
        addon_name = parsed.get("addon_name")
        if not addon_name:
            return [error("Usage: hop3 addon exists <name> [--type <type>]")]
        explicit = parsed.get("service_type") or parsed.get("type")
        types = _resolve_addon_types(addon_name)
        exists = (explicit in types) if explicit else bool(types)
        return [data({"exists": exists, "name": addon_name})]


@register
@dataclass(frozen=True)
class AddonExposeCmd(Command):
    """Expose an addon on a public host port (type-agnostic).

    Usage: hop3 addon expose <name> --source <cidr|any> [--host <fqdn>]

    Makes the addon reachable from outside the server on a stable, persisted
    port (a systemd-socket-proxyd forwarder to its loopback port) and prints a
    connection URL. The addon's type is resolved from its name.

    --source is required: a CIDR (e.g. 203.0.113.0/24), or `any` to open to the
    whole internet. The external host comes from --host, else the server's
    canonical domain.

    Examples:
        hop3 addon expose mydb --source 203.0.113.0/24
        hop3 addon expose mydb --source any --host db.example.com
    """

    port_claim_repo: PortClaimRepository
    name: ClassVar[tuple[str, ...]] = ("addon", "expose")
    requires_auth: ClassVar[bool] = True
    _arg_spec: ClassVar[dict] = {
        "addon_name": {"positional": True},
        "source": {"type": str},
        "host": {"type": str},
        "type": {"type": str},
        "service_type": {"type": str},
    }

    def call(self, *args):
        parsed = parse_cli_args(args, self._arg_spec)
        addon_name = parsed.get("addon_name")
        if not addon_name:
            return [
                text(
                    "Usage: hop3 addon expose <name> --source <cidr|any> [--host <fqdn>]"
                )
            ]
        explicit = parsed.get("service_type") or parsed.get("type")
        addon_type, errors = _resolve_one_type(addon_name, explicit)
        if errors:
            return errors
        assert addon_type is not None

        source = parsed.get("source") or config.EXPOSE_DEFAULT_SOURCE
        if not source:
            return [
                error(
                    "--source is required: a CIDR (e.g. 203.0.113.0/24), or 'any' "
                    "to open to the whole internet. Set EXPOSE_DEFAULT_SOURCE in "
                    "hop3-server.toml for a per-server default."
                )
            ]
        host = parsed.get("host") or config.ADMIN_DOMAIN
        if not host:
            return [
                error(
                    "No external host for the URL: pass --host <fqdn>, or set the "
                    "server's ADMIN_DOMAIN. A reachable hostname is required."
                )
            ]

        with command_context(
            "exposing addon", addon_name=addon_name, service_type=addon_type
        ):
            result = expose_addon(
                addon_type,
                addon_name,
                source=source,
                host=host,
                db_session=self.port_claim_repo.session,
            )

        items: list = [
            data(result),
            table(
                headers=["Field", "Value"],
                rows=[
                    ["Type", result["type"]],
                    ["Host", result["host"]],
                    ["Public port", str(result["public_port"])],
                    ["Source", result["source"]],
                    ["URL", result["url"]],
                ],
            ),
        ]
        if result["source"] == "any":
            items.append(
                warning(
                    "This addon is now reachable from the ENTIRE internet "
                    "(--source any). Only the addon credentials protect it — "
                    "scope it with --source <cidr> instead if you can."
                )
            )
        verb = "already exposed" if result.get("already_exposed") else "exposed"
        items.append(
            summary(
                f"{verb} addon '{addon_name}' ({addon_type}) on "
                f"{result['host']}:{result['public_port']}."
            )
        )
        return items


@register
@dataclass(frozen=True)
class AddonUnexposeCmd(Command):
    """Remove an addon's public exposure (type-agnostic).

    Usage: hop3 addon unexpose <name>

    Closes the public port, removes the forwarder, and frees the claim.
    Idempotent. The addon itself and its data are untouched.

    Examples:
        hop3 addon unexpose mydb
    """

    port_claim_repo: PortClaimRepository
    name: ClassVar[tuple[str, ...]] = ("addon", "unexpose")
    requires_auth: ClassVar[bool] = True
    _arg_spec: ClassVar[dict] = {
        "addon_name": {"positional": True},
        "type": {"type": str},
        "service_type": {"type": str},
    }

    def call(self, *args):
        parsed = parse_cli_args(args, self._arg_spec)
        addon_name = parsed.get("addon_name")
        if not addon_name:
            return [text("Usage: hop3 addon unexpose <name>")]
        explicit = parsed.get("service_type") or parsed.get("type")
        addon_type, errors = _resolve_one_type(addon_name, explicit)
        if errors:
            return errors
        assert addon_type is not None

        with command_context(
            "unexposing addon", addon_name=addon_name, service_type=addon_type
        ):
            removed = unexpose_addon(
                addon_type, addon_name, db_session=self.port_claim_repo.session
            )
        if not removed:
            return [text(f"Addon '{addon_name}' is not exposed.")]
        return [
            text(f"Removed public exposure of {addon_type} addon '{addon_name}'."),
            summary(f"unexposed addon '{addon_name}' ({addon_type})."),
        ]


@register
@dataclass(frozen=True)
class AddonPromoteCmd(Command):
    """Make an addon the primary one of its type for an app (type-agnostic).

    Usage: hop3 addon promote <name> --app <app> [--type <type>]

    When several same-type addons are attached to an app, the primary injects
    the UNPREFIXED connection vars (DATABASE_URL, …) and the others are prefixed
    (<NAME>_DATABASE_URL). This flips which one is primary; the previous primary
    becomes prefixed. Redeploy the app for the env change to take effect.

    Examples:
        hop3 addon promote db2 --app myapp
        hop3 addon promote db2 --app myapp --type postgres
    """

    app_repo: AppRepository
    addon_credential_repo: AddonCredentialRepository
    env_var_repo: EnvVarRepository
    name: ClassVar[tuple[str, ...]] = ("addon", "promote")
    requires_auth: ClassVar[bool] = True
    _arg_spec: ClassVar[dict] = {
        "addon_name": {"positional": True},
        "app": {"type": str},
        "type": {"type": str},
        "service_type": {"type": str},
    }

    def call(self, *args):
        parsed = parse_cli_args(args, self._arg_spec)
        addon_name = parsed.get("addon_name")
        app_name = parsed.get("app")
        if not addon_name or not app_name:
            return [
                text("Usage: hop3 addon promote <name> --app <app> [--type <type>]")
            ]

        explicit = parsed.get("service_type") or parsed.get("type")
        addon_type, errors = _resolve_one_type(addon_name, explicit)
        if errors:
            return errors
        assert addon_type is not None

        app = self.app_repo.get_one_or_none(name=app_name)
        if not app:
            return [error(f"App '{app_name}' not found.")]

        with command_context(
            "promoting addon", addon_name=addon_name, service_type=addon_type
        ):
            target = self.addon_credential_repo.get_by_app_addon(
                app.id, addon_type, addon_name
            )
            if target is None:
                return [
                    error(
                        f"Addon '{addon_name}' ({addon_type}) is not attached to "
                        f"'{app_name}'. Attach it first: "
                        f"hop3 addon attach {addon_name} --app {app_name}"
                    )
                ]
            if target.is_primary:
                return [
                    text(
                        f"Addon '{addon_name}' is already the primary {addon_type} "
                        f"for '{app_name}'."
                    )
                ]

            siblings = self.addon_credential_repo.list_by_app_and_type(
                app.id, addon_type
            )
            for cred in siblings:
                cred.is_primary = cred.addon_name == addon_name
            self.addon_credential_repo.session.flush()
            sync_addon_env_vars(app, self.addon_credential_repo.session)
            self.addon_credential_repo.session.commit()

        return [
            text(
                f"Promoted '{addon_name}' to the primary {addon_type} for "
                f"'{app_name}'; it now owns the unprefixed connection vars "
                "(DATABASE_URL). Redeploy for the change to take effect."
            ),
            summary(
                f"promoted addon '{addon_name}' ({addon_type}) to primary for "
                f"{app_name}."
            ),
        ]


@register
@dataclass(frozen=True)
class AddonTypesCmd(Command):
    """List available addon types.

    Shows all registered addon types that can be provisioned with
    'hop3 addon create <type> <name>'.

    Usage: hop3 addon types

    Examples:
        hop3 addon types               # List all addon types
    """

    name: ClassVar[tuple[str, ...]] = ("addon", "types")
    requires_auth: ClassVar[bool] = True

    def call(self, *args):
        """List available addon types."""
        server_log.info("addon types called")

        pm = get_plugin_manager()
        addon_classes_list = pm.hook.get_addons()
        addon_classes = [cls for sublist in addon_classes_list for cls in sublist]

        server_log.info(
            "addon types found addons",
            count=len(addon_classes),
            addon_types=[getattr(cls, "name", "?") for cls in addon_classes],
        )

        if not addon_classes:
            return [
                warning("No addon types registered."),
                text("Check that addon plugins are properly installed."),
            ]

        rows = []
        for addon_class in addon_classes:
            addon_name = getattr(addon_class, "name", "unknown")
            addon_module = addon_class.__module__
            rows.append([addon_name, addon_module])

        return [
            text("Available addon types:"),
            table(headers=["Type", "Module"], rows=rows),
        ]


@register
@dataclass(frozen=True)
class AddonCreateCmd(Command):
    """Create a new addon.

    Usage: hop3 addon create <type> <name>

    Examples:
        hop3 addon create postgres my-database
        hop3 addon create redis my-cache
    """

    name: ClassVar[tuple[str, ...]] = ("addon", "create")
    requires_auth: ClassVar[bool] = True

    def call(self, *args):
        """Create a new service instance."""
        server_log.info("addons create called", args=args)

        if len(args) < 2:
            return [
                text(
                    "Usage: hop3 addon create <type> <name>\n\n"
                    "Example:\n"
                    "  hop3 addon create postgres my-database"
                )
            ]

        service_type = args[0]
        addon_name = args[1]

        # addon_name flows into SQL identifier interpolation in some plugins
        # (e.g. MySQL `CREATE DATABASE \`{db_name}\``) where parameter binding
        # is not available for identifiers. Reject anything that isn't a
        # safe identifier before it ever reaches a plugin.
        try:
            validate_service_name(addon_name)
        except InvalidIdentifierError as exc:
            return [error(str(exc))]

        with command_context(
            "creating addon", addon_name=addon_name, service_type=service_type
        ):
            # Get the service strategy from the plugin system
            server_log.info(
                "addons create getting addon",
                service_type=service_type,
                addon_name=addon_name,
            )
            addon = get_addon(service_type, addon_name)

            # Create the service
            server_log.info("addons create calling addon.create()")
            addon.create()
            server_log.info("addons create addon.create() completed successfully")

        return [
            text(
                f"Addon '{addon_name}' of type '{service_type}' created successfully."
            ),
            text(
                f"\nTo attach this service to an app, run:\n  hop3 addon attach {addon_name} --app <app-name>"
            ),
            summary(f"created addon '{addon_name}' ({service_type})."),
        ]


@register
@dataclass(frozen=True)
class AddonAttachCmd(Command):
    """Attach an addon to an application.

    This command injects the service's connection details as environment
    variables into the specified application.

    Usage: hop3 addon attach <name> --app <app-name> [--type <type>]

    Examples:
        hop3 addon attach my-database --app my-app --type postgres
        hop3 addon attach my-cache --app my-app --type redis
    """

    app_repo: AppRepository
    addon_credential_repo: AddonCredentialRepository
    env_var_repo: EnvVarRepository
    name: ClassVar[tuple[str, ...]] = ("addon", "attach")
    # Argument specification for declarative parsing
    _arg_spec: ClassVar[dict] = {
        "addon_name": {"positional": True},
        "app": {"type": str},  # --app <name>
        "type": {"type": str, "default": "postgres"},  # --type <type>
        "service_type": {"type": str},  # --service-type <type> (preferred alias)
        "primary": {"flag": True, "default": False},  # attach as the primary
    }

    def _apply_primary(
        self, app_id: int, service_type: str, addon_name: str, *, want_primary: bool
    ) -> bool:
        """Decide + set which same-type addon is primary; return this one's status.

        First addon of a type → primary. A later one → non-primary, unless
        ``--primary`` is given or there is currently no primary at all. When this
        addon becomes primary, its same-type siblings are demoted in the same
        transaction (the one-primary-per-(app,type) invariant).
        """
        siblings = self.addon_credential_repo.list_by_app_and_type(app_id, service_type)
        this = next((c for c in siblings if c.addon_name == addon_name), None)
        if this is None:
            return False
        make_primary = (
            want_primary
            or len(siblings) == 1
            or not any(c.is_primary for c in siblings)
        )
        if make_primary:
            for cred in siblings:
                cred.is_primary = cred.addon_name == addon_name
            self.addon_credential_repo.session.flush()
        return this.is_primary

    def _store_or_update_credential(
        self,
        app_id: int,
        service_type: str,
        addon_name: str,
        connection_details: dict,
    ):
        """Store or update encrypted service credentials."""
        encryptor = get_credential_encryptor()

        existing_credential = self.addon_credential_repo.get_by_app_addon(
            app_id, service_type, addon_name
        )

        if existing_credential:
            existing_credential.encrypted_data = encryptor.encrypt(connection_details)
            self.addon_credential_repo.update(existing_credential)
        else:
            credential = AddonCredential(
                app_id=app_id,
                addon_type=service_type,
                addon_name=addon_name,
                encrypted_data=encryptor.encrypt(connection_details),
            )
            self.addon_credential_repo.add(credential)

    def call(self, *args):
        """Attach an addon to an application."""
        server_log.info("addons attach called", args=args)

        parsed = parse_cli_args(args, self._arg_spec)
        addon_name = parsed.get("addon_name")
        app_name = parsed.get("app")
        service_type = parsed.get("service_type") or parsed.get("type", "postgres")

        if not addon_name:
            return [
                text(
                    "Usage: hop3 addon attach <name> --app <app-name> [--type <type>]\n\n"
                    "Example:\n"
                    "  hop3 addon attach my-database --app my-app --type postgres"
                )
            ]

        server_log.info(
            "addons attach parsed args",
            addon_name=addon_name,
            app_name=app_name,
            service_type=service_type,
        )

        if not app_name:
            return [
                error(
                    "Error: --app parameter is required\n\n"
                    "Usage: hop3 addon attach <name> --app <app-name>"
                )
            ]

        with command_context(
            "attaching addon", addon_name=addon_name, app_name=app_name
        ):
            # Check if app exists
            app = self.app_repo.get_one_or_none(name=app_name)

            if not app:
                server_log.warning("addons attach app not found", app_name=app_name)
                msg = f"App '{app_name}' not found"
                raise ValueError(msg)

            server_log.info(
                "addons attach found app",
                app_name=app_name,
                app_id=app.id,
                current_env_vars_count=len(list(app.env_vars)),
            )

            # Get the service strategy and connection details
            addon = get_addon(service_type, addon_name)
            server_log.info(
                "addons attach got addon",
                addon_type=type(addon).__name__,
                addon_name=addon_name,
            )

            # Get connection details - this may raise RuntimeError if password not found
            connection_details = addon.get_connection_details()

            server_log.info(
                "addons attach got connection details",
                connection_details_keys=list(connection_details.keys()),
                has_database_url="DATABASE_URL" in connection_details,
            )

            if not connection_details:
                server_log.error("addons attach connection_details is empty!")
                msg = "No connection details returned from addon"
                raise ValueError(msg)

            # Store the credential, decide primary-ness, then materialize env
            # from all of the app's credentials (namespaced by primary).
            self._store_or_update_credential(
                app.id, service_type, addon_name, connection_details
            )
            self.addon_credential_repo.session.flush()
            is_primary = self._apply_primary(
                app.id,
                service_type,
                addon_name,
                want_primary=bool(parsed.get("primary")),
            )
            sync_report = sync_addon_env_vars(app, self.addon_credential_repo.session)
            self.addon_credential_repo.session.commit()
            server_log.info(
                "addons attach committed",
                app_id=app.id,
                is_primary=is_primary,
                set_vars=sync_report["set"],
            )

        set_vars = sync_report["set"]
        slot = "primary" if is_primary else "secondary"
        suffix = (
            ""
            if is_primary
            else f" as a secondary {service_type} (vars prefixed "
            f"'{addon_name.upper().replace('-', '_')}_')"
        )
        response = [
            text(
                f"Addon '{addon_name}' attached to app '{app_name}'{suffix}.",
            ),
        ]
        if set_vars:
            response.append(
                text("\nEnvironment variables:\n  " + "\n  ".join(set_vars))
            )
        else:
            response.append(warning("\nWARNING: No environment variables were added!"))
        response.append(
            text(
                f"\nRedeploy your app for changes to take effect:\n  hop3 deploy {app_name}"
            )
        )
        response.append(
            summary(
                f"attached addon '{addon_name}' ({service_type}, {slot}) to "
                f"{app_name}; {len(set_vars)} env var(s)."
            )
        )
        return response


@register
@dataclass(frozen=True)
class AddonDetachCmd(Command):
    """Detach an addon from an application.

    This removes the service's environment variables from the application.

    Usage: hop3 addon detach <name> --app <app-name> [--type <type>]


    Examples:
        hop3 addon detach mydb --app myapp   # Detach mydb from myapp
    """

    app_repo: AppRepository
    addon_credential_repo: AddonCredentialRepository
    env_var_repo: EnvVarRepository
    name: ClassVar[tuple[str, ...]] = ("addon", "detach")
    # Argument specification for declarative parsing
    _arg_spec: ClassVar[dict] = {
        "addon_name": {"positional": True},
        "app": {"type": str},  # --app <name>
        "type": {"type": str, "default": "postgres"},  # --type <type>
        "service_type": {"type": str},  # --service-type <type> (preferred alias)
    }

    def _addon_details(self, service_type: str, addon_name: str, stored: str) -> dict:
        """Decrypt the stored credential; fall back to the live addon."""
        encryptor = get_credential_encryptor()
        try:
            details = encryptor.decrypt(stored)
        except Exception:
            details = {}
        if details:
            return details
        try:
            return get_addon(service_type, addon_name).get_connection_details()
        except Exception:
            return {}

    def _remove_named_env_vars(self, app, names) -> list[str]:
        """Remove the app's env vars whose name is in ``names`` (delete-orphan)."""
        wanted = set(names)
        removed = []
        for env_var in list(app.env_vars):
            if env_var.name in wanted:
                app.env_vars.remove(env_var)
                removed.append(env_var.name)
        return removed

    def call(self, *args):
        """Detach an addon from an application."""
        parsed = parse_cli_args(args, self._arg_spec)
        addon_name = parsed.get("addon_name")
        app_name = parsed.get("app")
        service_type = parsed.get("service_type") or parsed.get("type", "postgres")

        if not addon_name:
            return [
                text(
                    "Usage: hop3 addon detach <name> --app <app-name> [--type <type>]\n\n"
                    "Example:\n"
                    "  hop3 addon detach my-database --app my-app"
                )
            ]

        if not app_name:
            return [error("Error: --app parameter is required")]

        with command_context(
            "detaching addon", addon_name=addon_name, app_name=app_name
        ):
            app = self.app_repo.get_one_or_none(name=app_name)
            if not app:
                msg = f"App '{app_name}' not found"
                raise ValueError(msg)

            credential = self.addon_credential_repo.get_by_app_addon(
                app.id, service_type, addon_name
            )
            if credential is None:
                return [
                    text(f"Addon '{addon_name}' was not attached to app '{app_name}'.")
                ]

            was_primary = credential.is_primary
            details = self._addon_details(
                service_type, addon_name, credential.encrypted_data
            )
            # Remove this addon's OWN env vars in BOTH spellings (unprefixed and
            # <NAME>_ prefixed) — robust whichever it was using. Must be explicit:
            # once the credential is deleted, sync no longer knows these names.
            prefix = addon_var_prefix(addon_name)
            own_names = set(details) | {f"{prefix}{key}" for key in details}
            removed_vars = self._remove_named_env_vars(app, own_names)

            self.addon_credential_repo.delete(credential.id)
            self.addon_credential_repo.session.flush()

            # If we removed the primary, auto-promote the oldest remaining sibling
            # so the app keeps an unprefixed DATABASE_URL.
            promoted = None
            if was_primary:
                siblings = self.addon_credential_repo.list_by_app_and_type(
                    app.id, service_type
                )
                if siblings:
                    siblings[0].is_primary = True  # oldest (ordered by id)
                    promoted = siblings[0].addon_name
                    self.addon_credential_repo.session.flush()

            # Re-materialize env: flips the promoted sibling's vars to unprefixed.
            sync_addon_env_vars(app, self.addon_credential_repo.session)
            self.addon_credential_repo.session.commit()

        items = [text(f"Addon '{addon_name}' detached from app '{app_name}'.")]
        if removed_vars:
            items.append(text(f"\nRemoved: {', '.join(sorted(removed_vars))}"))
        if promoted:
            items.append(
                text(
                    f"Auto-promoted '{promoted}' to primary {service_type}; it now "
                    "owns the unprefixed connection vars (DATABASE_URL)."
                )
            )
        promote_note = f"; promoted '{promoted}'" if promoted else ""
        items.append(
            summary(
                f"detached addon '{addon_name}' ({service_type}) from "
                f"{app_name}{promote_note}."
            )
        )
        return items


@register
@dataclass(frozen=True)
class AddonDestroyCmd(Command):
    """Destroy an addon.

    WARNING: This will permanently delete all data in the service!

    Usage: hop3 addon destroy <name> [--type <type>]


    Examples:
        hop3 addon destroy mydb        # Destroy an addon (prompts for confirmation)
    """

    addon_credential_repo: AddonCredentialRepository
    name: ClassVar[tuple[str, ...]] = ("addon", "destroy")
    destructive: ClassVar[bool] = True

    # Argument specification for declarative parsing
    _arg_spec: ClassVar[dict] = {
        "addon_name": {"positional": True},
        "type": {"type": str, "default": "postgres"},  # --type <type>
        "service_type": {"type": str},  # --service-type <type> (preferred alias)
    }

    def call(self, *args):
        """Destroy an addon."""
        parsed = parse_cli_args(args, self._arg_spec)
        addon_name = parsed.get("addon_name")
        service_type = parsed.get("service_type") or parsed.get("type", "postgres")

        if not addon_name:
            return [
                text(
                    "Usage: hop3 addon destroy <name> [--type <type>]\n\n"
                    "WARNING: This will permanently delete all data!\n\n"
                    "Example:\n"
                    "  hop3 addon destroy my-database --type postgres"
                )
            ]

        with command_context(
            "destroying addon", addon_name=addon_name, service_type=service_type
        ):
            # Get the service strategy
            addon = get_addon(service_type, addon_name)

            # Check if the addon actually exists (hasattr check doesn't narrow type for ty)
            if hasattr(addon, "exists") and not addon.exists():  # type: ignore[call-non-callable]
                return [
                    text(
                        f"Addon '{addon_name}' of type '{service_type}' does not exist."
                    )
                ]

            # Tear down any public exposure first (close the port before the data
            # is touched). Idempotent — a no-op when the addon isn't exposed. The
            # app-delete cascade doesn't cover addon claims (app_id is null), so
            # this explicit call is mandatory, not a backstop.
            unexpose_addon(
                service_type,
                addon_name,
                db_session=self.addon_credential_repo.session,
            )

            # Clean up all stored credentials for this service
            credentials = self.addon_credential_repo.list_by_addon(
                service_type, addon_name
            )

            for credential in credentials:
                self.addon_credential_repo.delete(credential.id)

            self.addon_credential_repo.session.commit()

            # Destroy the service
            addon.destroy()

        return [
            text(
                f"Addon '{addon_name}' of type '{service_type}' destroyed successfully."
            ),
            summary(f"destroyed addon '{addon_name}' ({service_type})."),
        ]


@register
@dataclass(frozen=True)
class AddonShowCmd(Command):
    """Show information about an addon.

    Usage: hop3 addon show <name> [--type <type>]


    Examples:
        hop3 addon show mydb           # Show addon details
        hop3 addon show mydb --type postgres
    """

    name: ClassVar[tuple[str, ...]] = ("addon", "show")
    requires_auth: ClassVar[bool] = True

    # Argument specification for declarative parsing
    _arg_spec: ClassVar[dict] = {
        "addon_name": {"positional": True},
        "type": {"type": str, "default": "postgres"},  # --type <type>
        "service_type": {"type": str},  # --service-type <type> (preferred alias)
    }

    def call(self, *args):
        """Get service information."""
        parsed = parse_cli_args(args, self._arg_spec)
        addon_name = parsed.get("addon_name")
        service_type = parsed.get("service_type") or parsed.get("type", "postgres")

        if not addon_name:
            return [
                text(
                    "Usage: hop3 addon show <name> [--type <type>]\n\n"
                    "Example:\n"
                    "  hop3 addon show my-database --type postgres"
                )
            ]

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

        return [text("\n".join(lines))]


@register
@dataclass(frozen=True)
class AddonStatusCmd(Command):
    """Show detailed status and health of an addon.

    Performs a health check on the addon and shows all attached applications.

    Usage: hop3 addon status <name> [--type <type>]

    Examples:
        hop3 addon status my-database --type postgres
        hop3 addon status my-cache --type redis
    """

    addon_credential_repo: AddonCredentialRepository
    name: ClassVar[tuple[str, ...]] = ("addon", "status")
    # Argument specification for declarative parsing
    _arg_spec: ClassVar[dict] = {
        "addon_name": {"positional": True},
        "service_type": {"type": str, "default": "postgres"},
    }

    def call(self, *args):
        """Get detailed addon status with health check."""
        parsed = parse_cli_args(args, self._arg_spec)
        addon_name = parsed.get("addon_name")

        if not addon_name:
            return self._usage_message()

        service_type = parsed["type"]

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

        return [table(headers=["Property", "Value"], rows=rows)]

    def _usage_message(self) -> list[dict]:
        """Return usage message."""
        return [
            text(
                "Usage: hop3 addon status <name> [--type <type>]\n\n"
                "Example:\n"
                "  hop3 addon status my-database --type postgres"
            )
        ]

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
        credentials = self.addon_credential_repo.list_by_addon(service_type, addon_name)
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
