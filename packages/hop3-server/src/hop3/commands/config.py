# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands."""

from __future__ import annotations

from pathlib import Path

from hop3.lib.registry import register
from hop3.orm import App
from hop3.project.procfile import Procfile

from ._base import Command


def get_app(app_name):
    return App()


@register
class ConfigCmd(Command):
    """Manage an application config / env."""

    name = "config"


@register
class ShowCmd(Command):
    """Show config, e.g.: hop config <app>."""

    name = "config:show"

    def call(self, app_name):
        app = get_app(app_name)
        env = app.get_env()

        rows = [[k, v] for k, v in env.items()]
        return [
            {
                "t": "table",
                "headers": ["Key", "Value"],
                "rows": rows,
            }
        ]


@register
class GetCmd(Command):
    """e.g.: hop config:get <app> FOO."""

    name = "config:get"

    def call(self, app_name, setting):
        app = get_app(app_name)
        env = app.get_env()
        if setting in env:
            return [{"t": "text", "text": env[setting]}]
        else:
            return [{"t": "text", "text": f"Setting '{setting}' not found."}]


@register
class LiveCmd(Command):
    """e.g.: hop config:live <app>."""

    name = "config:live"

    def call(self, app_name):
        app = get_app(app_name)
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
class MigrateProcfileCmd(Command):
    """Convert Procfile to hop3.toml format.

    Example: hop config:migrate-procfile <app_dir> [--dry-run] [--backup]
    """

    name = "config:migrate-procfile"

    def call(self, app_dir: str, dry_run: bool = False, backup: bool = True):
        """Convert a Procfile to hop3.toml format.

        Args:
            app_dir: Path to the application directory
            dry_run: If True, show what would be generated without writing
            backup: If True, create backup of original Procfile
        """
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
