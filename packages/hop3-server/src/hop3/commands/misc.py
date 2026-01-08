# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Miscellaneous and addon-related CLI commands."""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.metadata import version as get_version
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from hop3 import config as c
from hop3.deployers import do_deploy
from hop3.lib.registry import lookup, register
from hop3.orm import App, AppRepository
from hop3.project.procfile import parse_procfile

from ._base import Command
from ._errors import command_context

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


# --- Version Command ---


@register
@dataclass(frozen=True)
class VersionCmd(Command):
    """Show version information."""

    name: ClassVar[str] = "version"
    requires_auth: ClassVar[bool] = False  # Public command

    def call(self, *args):
        try:
            server_version = get_version("hop3-server")
        except Exception:
            server_version = "unknown"

        return [
            {"t": "text", "text": f"hop3-server {server_version}"},
        ]


# --- Backup Command ---


@register
@dataclass(frozen=True)
class BackupCmd(Command):
    """Run a backup for an app's source code and virtual environment."""

    db_session: Session
    name: ClassVar[str] = "backup"

    def call(self, *args):
        if not args:
            msg = "Usage: hop backup <app_name>"
            raise ValueError(msg)
        app_name = args[0]
        app = _get_app(self.db_session, app_name)

        # POC implementation
        path_to_backup = app.app_path
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d-%H%M%S")
        backup_name = f"{app.name}-{timestamp}.tar.gz"
        backup_dir = c.HOP3_ROOT / "backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_file_path = backup_dir / backup_name

        cmd = [
            "tar",
            "-zcf",
            str(backup_file_path),
            "-C",
            str(path_to_backup.parent),
            path_to_backup.name,
        ]
        with command_context("creating backup", app_name=app_name):
            subprocess.run(cmd, check=True, capture_output=True, text=True)

        return [
            {"t": "text", "text": f"Backup for {app.name} created successfully."},
            {"t": "text", "text": f"Location: {backup_file_path}"},
        ]


# --- Plugins Command ---


@register
@dataclass(frozen=True)
class PluginsCmd(Command):
    """List installed plugins and their commands."""

    name: ClassVar[str] = "plugins"

    def call(self, *args):
        # This implementation introspects the command registry
        all_commands = lookup(Command)
        command_groups: dict[str, list[str]] = {}
        for cmd_class in sorted(all_commands, key=lambda c: c.name):
            module_name = cmd_class.__module__
            if module_name.startswith("hop3.plugins."):
                plugin_name = module_name.split(".")[2]
                if plugin_name not in command_groups:
                    command_groups[plugin_name] = []
                command_groups[plugin_name].append(cmd_class.name)

        if not command_groups:
            return [{"t": "text", "text": "No external plugins with commands found."}]

        rows = []
        for plugin, cmds in command_groups.items():
            rows.append([plugin, ", ".join(sorted(cmds))])

        return [
            {"t": "table", "headers": ["Plugin", "Provided Commands"], "rows": rows}
        ]


# --- Process Status & Scaling (ps, ps:scale) ---


@register
@dataclass(frozen=True)
class PSCmd(Command):
    """Show process count for an app."""

    db_session: Session
    name: ClassVar[str] = "ps"

    def call(self, *args):
        if not args:
            msg = "Usage: hop ps <app_name>"
            raise ValueError(msg)
        app_name = args[0]
        app = _get_app(self.db_session, app_name)
        scaling_file = app.virtualenv_path / "SCALING"

        if not scaling_file.exists():
            return [
                {
                    "t": "text",
                    "text": f"No process information found for app '{app_name}'. Has it been deployed?",
                }
            ]

        worker_map = parse_procfile(scaling_file)
        rows = [[proc_type, count] for proc_type, count in worker_map.items()]
        return [{"t": "table", "headers": ["Process Type", "Count"], "rows": rows}]


# The subcommand ps:scale will be handled by the main `ps` command group.
@register
@dataclass(frozen=True)
class PsScaleCmd(Command):
    """Set the process count (e.g., hop ps:scale <app_name> web=2 worker=1)."""

    db_session: Session
    name: ClassVar[str] = "ps:scale"

    def call(self, *args):
        if len(args) < 2:
            return [
                {
                    "t": "text",
                    "text": "Usage: hop ps:scale <app_name> <type>=<count>...",
                }
            ]

        app_name = args[0]
        settings = args[1:]
        app = _get_app(self.db_session, app_name)

        scaling_file = app.virtualenv_path / "SCALING"
        if not scaling_file.exists():
            return [
                {
                    "t": "text",
                    "text": f"Cannot scale app '{app_name}'. Has it been deployed?",
                }
            ]

        worker_count = parse_procfile(scaling_file)
        deltas: dict[str, int] = {}

        for s in settings:
            try:
                key, value = s.split("=", 1)
                key = key.strip()
                count = int(value.strip())
            except ValueError:
                return [{"t": "text", "text": f"Error: malformed setting '{s}'"}]

            if count < 0:
                return [{"t": "text", "text": f"Error: cannot scale '{key}' below 0"}]
            if key not in worker_count:
                return [
                    {
                        "t": "text",
                        "text": f"Error: process type '{key}' not found for app '{app_name}'",
                    }
                ]

            deltas[key] = count - int(worker_count[key])

        with command_context("scaling app", app_name=app_name):
            do_deploy(app, deltas=deltas)

        return [{"t": "text", "text": f"Scaling app '{app_name}'..."}]


# --- Run Command ---


@register
@dataclass(frozen=True)
class RunCmd(Command):
    """Run a command in the context of an app."""

    db_session: Session
    name: ClassVar[str] = "run"

    def call(self, *args):
        if len(args) < 2:
            return [
                {"t": "text", "text": "Usage: hop run <app_name> <command> [args...]"}
            ]

        app_name = args[0]
        cmd_to_run = args[1:]
        app = _get_app(self.db_session, app_name)

        try:
            result = subprocess.run(
                cmd_to_run,
                cwd=app.src_path,
                env=app.get_runtime_env(),
                check=True,
                capture_output=True,
                text=True,
            )
            output = result.stdout
            if result.stderr:
                output += f"\n--- stderr ---\n{result.stderr}"
            return [{"t": "text", "text": output}]
        except FileNotFoundError:
            return [
                {"t": "text", "text": f"Error: command not found: '{cmd_to_run[0]}'"}
            ]
        except subprocess.CalledProcessError as e:
            output = e.stdout
            if e.stderr:
                output += f"\n--- stderr ---\n{e.stderr}"
            return [
                {
                    "t": "text",
                    "text": f"Command failed with exit code {e.returncode}:\n{output}",
                }
            ]


# --- SBOM Command ---


@register
@dataclass(frozen=True)
class SbomCmd(Command):
    """Generate a Software Bill of Materials (SBOM) for an app."""

    db_session: Session
    name: ClassVar[str] = "sbom"

    def call(self, *args):
        if not args:
            msg = "Usage: hop sbom <app_name>"
            raise ValueError(msg)
        app_name = args[0]
        app = _get_app(self.db_session, app_name)

        # This is a Python-specific POC. A real implementation would be pluggable.
        venv = app.virtualenv_path
        if not (venv / "bin" / "pip").exists():
            return [
                {
                    "t": "text",
                    "text": "SBOM generation for Python requires a pip virtualenv. App may not be a Python app or may not be deployed.",
                }
            ]

        cyclonedx_path = c.HOP3_ROOT / "venv/bin/cyclonedx-py"
        if not cyclonedx_path.exists():
            return [
                {
                    "t": "text",
                    "text": f"Error: cyclonedx-py not found at {cyclonedx_path}",
                }
            ]

        with tempfile.TemporaryDirectory() as tmpdir:
            req_file = Path(tmpdir) / "requirements.txt"
            sbom_file = Path(tmpdir) / "sbom.json"

            # Generate requirements.txt from pip
            pip_cmd = f"{venv}/bin/pip list --format=freeze > {req_file}"
            subprocess.run(pip_cmd, shell=True, check=True)

            # Generate SBOM from requirements.txt
            sbom_cmd = [
                str(cyclonedx_path),
                "requirements",
                "-o",
                str(sbom_file),
                str(req_file),
            ]
            subprocess.run(sbom_cmd, check=True)

            sbom_content = sbom_file.read_text()
            return [{"t": "text", "text": sbom_content}]


# --- Addon Command Aliases ---
# These provide user-friendly shortcuts to the addons:* commands


@register
@dataclass(frozen=True)
class PgCmd(Command):
    """Manage PostgreSQL databases.

    PostgreSQL databases are managed via the addons:* commands.

    Examples:
        hop3 addons:create postgres my-database
        hop3 addons:attach my-database --app my-app --service-type postgres
        hop3 addons:info my-database --service-type postgres
        hop3 addons:detach my-database --app my-app --service-type postgres
        hop3 addons:destroy my-database --service-type postgres
    """

    name: ClassVar[str] = "pg"

    def call(self, *args):
        return [
            {
                "t": "text",
                "text": (
                    "PostgreSQL databases are managed via the addons:* commands.\n\n"
                    "Examples:\n"
                    "  hop3 addons:create postgres my-database\n"
                    "  hop3 addons:attach my-database --app my-app --service-type postgres\n"
                    "  hop3 addons:info my-database --service-type postgres\n"
                    "  hop3 addons:detach my-database --app my-app --service-type postgres\n"
                    "  hop3 addons:destroy my-database --service-type postgres\n\n"
                    "Run 'hop3 help --all' to see all addons:* commands."
                ),
            }
        ]


@register
@dataclass(frozen=True)
class RedisCmd(Command):
    """Manage Redis instances.

    Redis instances are managed via the addons:* commands.

    Examples:
        hop3 addons:create redis my-cache
        hop3 addons:attach my-cache --app my-app --service-type redis
        hop3 addons:info my-cache --service-type redis
        hop3 addons:destroy my-cache --service-type redis
    """

    name: ClassVar[str] = "redis"

    def call(self, *args):
        return [
            {
                "t": "text",
                "text": (
                    "Redis instances are managed via the addons:* commands.\n\n"
                    "Examples:\n"
                    "  hop3 addons:create redis my-cache\n"
                    "  hop3 addons:attach my-cache --app my-app --service-type redis\n"
                    "  hop3 addons:info my-cache --service-type redis\n"
                    "  hop3 addons:destroy my-cache --service-type redis\n\n"
                    "Run 'hop3 help --all' to see all addons:* commands."
                ),
            }
        ]
