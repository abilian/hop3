# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for configuration management."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from hop3.lib.registry import register
from hop3.orm import App, AppRepository, EnvVar
from hop3.project.procfile import Procfile

from ._base import Command

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _get_app(db_session: Session, app_name: str) -> App:
    """Helper to retrieve an app or raise a consistent error."""
    app_repo = AppRepository(session=db_session)
    app = app_repo.get_one_or_none(name=app_name)
    if not app:
        msg = f"App '{app_name}' not found."
        raise ValueError(msg)
    return app


@register
class ConfigCmd(Command):
    """Manage an application config / env."""

    name = "config"


@register
@dataclass(frozen=True)
class ShowCmd(Command):
    """Show config, e.g.: hop config <app>."""

    db_session: Session
    name = "config:show"

    def call(self, app_name):
        app = _get_app(self.db_session, app_name)
        env = app.get_runtime_env()

        rows = [[k, v] for k, v in env.items()]
        return [
            {
                "t": "table",
                "headers": ["Key", "Value"],
                "rows": rows,
            }
        ]


@register
@dataclass(frozen=True)
class GetCmd(Command):
    """e.g.: hop config:get <app> FOO."""

    db_session: Session
    name = "config:get"

    def call(self, app_name, setting):
        app = _get_app(self.db_session, app_name)
        env = app.get_runtime_env()
        if setting in env:
            return [{"t": "text", "text": env[setting]}]
        return [{"t": "text", "text": f"Setting '{setting}' not found."}]


@register
@dataclass(frozen=True)
class LiveCmd(Command):
    """e.g.: hop config:live <app>."""

    db_session: Session
    name = "config:live"

    def call(self, app_name):
        app = _get_app(self.db_session, app_name)
        env = app.get_runtime_env()

        if not env:
            return [
                {
                    "t": "text",
                    "text": f"Warning: app '{app_name}' not deployed, no config found.",
                }
            ]

        rows = [[k, v] for k, v in env.items()]
        return [
            {
                "t": "table",
                "headers": ["Key", "Value"],
                "rows": rows,
            }
        ]


@register
@dataclass(frozen=True)
class SetCmd(Command):
    """Set environment variables for an app.

    Usage: hop config:set <app> KEY=VALUE [KEY2=VALUE2 ...]

    Examples:
        hop config:set myapp DEBUG=true
        hop config:set myapp DATABASE_URL=postgres://... REDIS_URL=redis://...
    """

    db_session: Session
    name = "config:set"

    def call(self, app_name, *settings):
        if not settings:
            return [
                {
                    "t": "text",
                    "text": "Usage: hop config:set <app> KEY=VALUE [KEY2=VALUE2 ...]\n"
                    "Example: hop config:set myapp DEBUG=true",
                }
            ]

        app = _get_app(self.db_session, app_name)

        # Parse settings
        changes = []
        errors = []
        for setting in settings:
            if "=" not in setting:
                errors.append(
                    f"Invalid setting format: '{setting}' (expected KEY=VALUE)"
                )
                continue

            key, value = setting.split("=", 1)
            key = key.strip()
            value = value.strip()

            if not key:
                errors.append(f"Empty key in setting: '{setting}'")
                continue

            # Check if variable already exists
            existing = None
            for env_var in app.env_vars:
                if env_var.name == key:
                    existing = env_var
                    break

            if existing:
                old_value = existing.value
                existing.value = value
                changes.append(f"Updated {key}={value} (was: {old_value})")
            else:
                new_var = EnvVar(name=key, value=value, app=app)
                app.env_vars.append(new_var)
                changes.append(f"Set {key}={value}")

        if errors:
            return [{"t": "error", "text": "\n".join(errors)}]

        # Commit changes to database
        self.db_session.commit()

        result = [
            {"t": "text", "text": f"Updated configuration for '{app_name}':"},
        ]
        for change in changes:
            result.append({"t": "text", "text": f"  • {change}"})

        result.append({
            "t": "text",
            "text": "\nNote: Run 'hop app:restart <app>' to apply changes to running app.",
        })

        return result


@register
@dataclass(frozen=True)
class UnsetCmd(Command):
    """Unset environment variables for an app.

    Usage: hop config:unset <app> KEY [KEY2 ...]

    Examples:
        hop config:unset myapp DEBUG
        hop config:unset myapp DATABASE_URL REDIS_URL
    """

    db_session: Session
    name = "config:unset"

    def call(self, app_name, *keys):
        if not keys:
            return [
                {
                    "t": "text",
                    "text": "Usage: hop config:unset <app> KEY [KEY2 ...]\n"
                    "Example: hop config:unset myapp DEBUG",
                }
            ]

        app = _get_app(self.db_session, app_name)

        # Remove specified variables
        removed = []
        not_found = []
        for raw_key in keys:
            key = raw_key.strip()
            if not key:
                continue

            found = False
            for env_var in app.env_vars:
                if env_var.name == key:
                    app.env_vars.remove(env_var)
                    removed.append(key)
                    found = True
                    break

            if not found:
                not_found.append(key)

        # Commit changes to database
        self.db_session.commit()

        result = []
        if removed:
            result.append({
                "t": "text",
                "text": f"Removed configuration from '{app_name}':",
            })
            for key in removed:
                result.append({"t": "text", "text": f"  • {key}"})

        if not_found:
            result.append({"t": "text", "text": "\nNot found:"})
            for key in not_found:
                result.append({"t": "text", "text": f"  • {key}"})

        if removed:
            result.append({
                "t": "text",
                "text": "\nNote: Run 'hop app:restart <app>' to apply changes to running app.",
            })

        return result


@register
class MigrateCmd(Command):
    """Migrate configuration from other PaaS formats to hop3.toml."""

    name = "config:migrate"

    def call(
        self,
        from_format: str = "",
        app_dir: str = "",
        dry_run: bool = False,
        backup: bool = True,
    ):
        """Migrate configuration from other PaaS formats to hop3.toml.

        Args:
            from_format: Source format to migrate from (e.g., 'procfile')
            app_dir: Path to the application directory
            dry_run: If True, show what would be generated without writing
            backup: If True, create backup of original file
        """
        if not from_format or not app_dir:
            return [
                {
                    "t": "text",
                    "text": (
                        "Usage: hop config:migrate <from-format> <app-dir> [--dry-run] [--backup]\n\n"
                        "Supported formats:\n"
                        "  procfile    Convert Procfile to hop3.toml\n\n"
                        "Example:\n"
                        "  hop config:migrate procfile /path/to/app"
                    ),
                }
            ]

        if from_format.lower() != "procfile":
            return [
                {
                    "t": "error",
                    "text": f"Unsupported format: {from_format}. Currently only 'procfile' is supported.",
                }
            ]

        app_path = Path(app_dir)
        if not app_path.exists():
            return [{"t": "error", "text": f"Directory not found: {app_dir}"}]

        # Look for Procfile in standard locations
        procfile_path = None
        for location in [
            app_path / "Procfile",
            app_path / "src" / "Procfile",
            app_path / "src" / "hop3" / "Procfile",
        ]:
            if location.exists():
                procfile_path = location
                break

        if not procfile_path:
            return [{"t": "error", "text": f"Procfile not found in {app_dir}"}]

        # Parse the Procfile
        try:
            procfile = Procfile.from_file(procfile_path)
        except Exception as e:
            return [{"t": "error", "text": f"Failed to parse Procfile: {e}"}]

        # Generate hop3.toml content
        toml_content = self._generate_hop3_toml(procfile)

        if dry_run:
            return [
                {"t": "text", "text": "Generated hop3.toml content (dry-run):"},
                {"t": "text", "text": ""},
                {"t": "text", "text": toml_content},
            ]

        # Create backup if requested
        if backup:
            backup_path = procfile_path.with_suffix(".bak")
            backup_path.write_text(procfile_path.read_text())

        # Write hop3.toml
        output_path = procfile_path.parent / "hop3.toml"
        if output_path.exists():
            return [
                {
                    "t": "error",
                    "text": f"hop3.toml already exists at {output_path}. Remove it first or use --force.",
                }
            ]

        output_path.write_text(toml_content)

        return [
            {"t": "success", "text": "Successfully converted Procfile to hop3.toml"},
            {"t": "text", "text": f"Created: {output_path}"},
            {
                "t": "text",
                "text": f"Backup: {backup_path}" if backup else "",
            },
        ]

    def _generate_hop3_toml(self, procfile: Procfile) -> str:
        """Generate hop3.toml content from a Procfile.

        Args:
            procfile: Parsed Procfile object

        Returns:
            TOML-formatted string
        """
        lines = []
        lines.append("# hop3.toml - Generated from Procfile")
        lines.append("# Convention over Configuration")
        lines.append("")

        # Add metadata section (placeholder)
        lines.append("[metadata]")
        lines.append('id = "my-app"  # TODO: Replace with your app ID')
        lines.append('version = "1.0.0"')
        lines.append("")

        # Extract special workers (prebuild, prerun)
        workers = procfile.workers
        has_build = False
        has_run = False

        # Build section
        if "prebuild" in workers:
            lines.append("[build]")
            lines.append(f'before-build = "{workers["prebuild"]}"')
            lines.append("")
            has_build = True

        # Run section
        run_workers = {}
        if "web" in workers:
            run_workers["start"] = workers["web"]
        if "prerun" in workers:
            run_workers["before-run"] = workers["prerun"]

        if run_workers:
            lines.append("[run]")
            for key, value in run_workers.items():
                lines.append(f'{key} = "{value}"')
            lines.append("")
            has_run = True

        # Other workers (worker, cron, etc.)
        other_workers = {
            k: v
            for k, v in workers.items()
            if k not in {"web", "prebuild", "postbuild", "prerun"}
        }

        if other_workers:
            lines.append("# Additional workers from Procfile")
            lines.append("# Note: These may need manual integration into [run] section")
            for name, command in other_workers.items():
                lines.append(f"# {name}: {command}")
            lines.append("")

        return "\n".join(lines)


# @hop3.command("config:live")
# @argument("app")
# def cmd_config_live(app) -> None:
#     """e.g.: hop config:live <app>."""
#     app_obj = get_app(app)
#     env = app_obj.get_runtime_env()
#
#     if not env:
#         log(f"Warning: app '{app}' not deployed, no config found.", fg="yellow")
#         return
#
#     for k, v in sorted(env.items()):
#         log(f"{k}={v}", fg="white")


# @hop3.command("config:set")
# @argument("app")
# @argument("settings", nargs=-1)
# def cmd_config_set(app, settings) -> None:
#     """e.g.: hop config:set <app> FOO=bar BAZ=quux."""
#     app_obj = get_app(app)
#     env = app_obj.get_runtime_env()
#
#     for s in settings:
#         try:
#             key, value = s.split("=", 1)
#             key = key.strip()
#             value = value.strip()
#             log(f"Setting {key:s}={value} for '{app:s}'", fg="white")
#             env[key] = value
#         except Exception:
#             raise Abort(f"Error: malformed setting '{s}'")
#
#     config_file = Path(ENV_ROOT, app, "ENV")
#     write_settings(config_file, env)
#     do_deploy(app)
#
#
# @hop3.command("config:unset")
# @argument("app")
# @argument("settings", nargs=-1)
# def cmd_config_unset(app, settings) -> None:
#     """e.g.: hop config:unset <app> FOO."""
#     app_obj = get_app(app)
#     env = app_obj.get_runtime_env()
#
#     for s in settings:
#         if s in env:
#             del env[s]
#             log(f"Unsetting {s} for '{app}'")
#
#     config_file = Path(ENV_ROOT, app, "ENV")
#     write_settings(config_file, env)
#     do_deploy(app)
#
#
# @hop3.command("config:live")
# @argument("app")
# def cmd_config_live(app) -> None:
#     """e.g.: hop config:live <app>."""
#     app_obj = get_app(app)
#     env = app_obj.get_runtime_env()
#
#     if not env:
#         log(f"Warning: app '{app}' not deployed, no config found.", fg="yellow")
#         return
#
#     for k, v in sorted(env.items()):
#         log(f"{k}={v}", fg="white")
