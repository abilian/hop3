# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Miscellaneous and addon-related CLI commands."""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from importlib.metadata import version as get_version
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from hop3 import config as c
from hop3.deployers import do_deploy
from hop3.lib.registry import lookup, register
from hop3.lib.util import CommandError, CommandFailedError, run_command
from hop3.project.procfile import parse_procfile

from ._base import Command
from ._errors import command_context
from ._helpers import get_app
from ._response import error, table, text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


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

        return [text(f"hop3-server {server_version}")]


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
            return [text("No external plugins with commands found.")]

        rows = []
        for plugin, cmds in command_groups.items():
            rows.append([plugin, ", ".join(sorted(cmds))])

        return [table(headers=["Plugin", "Provided Commands"], rows=rows)]


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
        app = get_app(self.db_session, app_name)
        scaling_file = app.virtualenv_path / "SCALING"

        if not scaling_file.exists():
            return [
                text(
                    f"No process information found for app '{app_name}'. Has it been deployed?"
                )
            ]

        worker_map = parse_procfile(scaling_file)
        rows = [[proc_type, count] for proc_type, count in worker_map.items()]
        return [table(headers=["Process Type", "Count"], rows=rows)]


# The subcommand ps:scale will be handled by the main `ps` command group.
@register
@dataclass(frozen=True)
class PsScaleCmd(Command):
    """Set the process count (e.g., hop ps:scale <app_name> web=2 worker=1)."""

    db_session: Session
    name: ClassVar[str] = "ps:scale"

    def call(self, *args):
        if len(args) < 2:
            return [text("Usage: hop ps:scale <app_name> <type>=<count>...")]

        app_name = args[0]
        settings = args[1:]
        app = get_app(self.db_session, app_name)

        scaling_file = app.virtualenv_path / "SCALING"
        if not scaling_file.exists():
            return [text(f"Cannot scale app '{app_name}'. Has it been deployed?")]

        worker_count = parse_procfile(scaling_file)
        deltas: dict[str, int] = {}

        for s in settings:
            try:
                key, value = s.split("=", 1)
                key = key.strip()
                count = int(value.strip())
            except ValueError:
                return [error(f"Malformed setting '{s}'")]

            if count < 0:
                return [error(f"Cannot scale '{key}' below 0")]
            if key not in worker_count:
                return [error(f"Process type '{key}' not found for app '{app_name}'")]

            deltas[key] = count - int(worker_count[key])

        with command_context("scaling app", app_name=app_name):
            do_deploy(app, deltas=deltas, db_session=self.db_session)
            # Persist changes to database (run_state, port, etc.)
            self.db_session.commit()

        return [text(f"Scaling app '{app_name}'...")]


# --- Run Command ---


@register
@dataclass(frozen=True)
class RunCmd(Command):
    """Run a command in the context of an app."""

    db_session: Session
    name: ClassVar[str] = "run"

    def call(self, *args):
        if len(args) < 2:
            return [text("Usage: hop run <app_name> <command> [args...]")]

        app_name = args[0]
        cmd_to_run = list(args[1:])
        app = get_app(self.db_session, app_name)

        try:
            result = run_command(
                cmd_to_run,
                cwd=app.src_path,
                env=dict(app.get_runtime_env()),
                text=True,
                timeout=300,  # 5 minute timeout for user commands
            )
            output = result.stdout
            if result.stderr:
                output += f"\n--- stderr ---\n{result.stderr}"
            return [text(output)]
        except CommandFailedError as e:
            output = f"Command failed with exit code {e.returncode}"
            if e.stderr:
                output += f":\n{e.stderr}"
            return [error(output)]
        except CommandError as e:
            return [error(e.message)]


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
        app = get_app(self.db_session, app_name)

        # This is a Python-specific POC. A real implementation would be pluggable.
        venv = app.virtualenv_path
        if not (venv / "bin" / "pip").exists():
            return [
                text(
                    "SBOM generation for Python requires a pip virtualenv. "
                    "App may not be a Python app or may not be deployed."
                )
            ]

        cyclonedx_path = c.HOP3_ROOT / "venv/bin/cyclonedx-py"
        if not cyclonedx_path.exists():
            return [error(f"cyclonedx-py not found at {cyclonedx_path}")]

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
            return [text(sbom_content)]


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

    Run 'hop3 help addons' or 'hop3 help --all' to see all addons:* commands.
    """

    name: ClassVar[str] = "pg"

    def call(self, *args):
        # Return the docstring as help text
        return [text((self.__doc__ or "").strip())]


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

    Run 'hop3 help addons' or 'hop3 help --all' to see all addons:* commands.
    """

    name: ClassVar[str] = "redis"

    def call(self, *args):
        # Return the docstring as help text
        return [text((self.__doc__ or "").strip())]
