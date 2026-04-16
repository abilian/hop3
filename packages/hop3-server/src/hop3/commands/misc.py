# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Miscellaneous CLI commands."""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from importlib.metadata import version as get_version
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from hop3 import config as c
from hop3.config import HOP3_ROOT, HOP3_USER
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

    name: ClassVar[tuple[str, ...]] = ("version",)
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

    # Canonical name is `plugin list` per ADR 036 D9 (plural `plugins` is the
    # alias, resolved client-side in `hop3_cli.core.aliases.CORE_ALIASES`).
    name: ClassVar[tuple[str, ...]] = ("plugin", "list")

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


# --- Process Status & Scaling (ps, ps scale) ---


@register
@dataclass(frozen=True)
class PSCmd(Command):
    """Show process count for an app."""

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("ps",)

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


# The subcommand ps scale will be handled by the main `ps` command group.
@register
@dataclass(frozen=True)
class PsScaleCmd(Command):
    """Set the process count (e.g., hop ps scale <app_name> web=2 worker=1)."""

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("ps", "scale")

    def call(self, *args):
        if len(args) < 2:
            return [text("Usage: hop ps scale <app_name> <type>=<count>...")]

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
    """Run a command in the context of an app.

    Usage: hop run <app_name> <command> [args...] [--input <data>]

    Options:
        --input <data>: Data to send to command's stdin (for non-interactive input)

    Examples:
        hop run myapp flask db upgrade
        hop run myapp python manage.py migrate
        hop run myapp flask users change_password user@example.com --input "newpassword"
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("run",)

    def call(self, *args):
        if len(args) < 2:
            return [
                text(
                    "Usage: hop run <app_name> <command> [args...] [--input <data>]\n\n"
                    "Options:\n"
                    "  --input <data>  Data to send to stdin (for password prompts, etc.)"
                )
            ]

        # Parse --input option
        args_list = list(args)
        stdin_data = None
        if "--input" in args_list:
            idx = args_list.index("--input")
            if idx + 1 < len(args_list):
                stdin_data = args_list[idx + 1] + "\n"  # Add newline for input
                args_list = args_list[:idx] + args_list[idx + 2 :]
            else:
                return [error("--input requires a value")]

        app_name = args_list[0]
        cmd_to_run = args_list[1:]
        app = get_app(self.db_session, app_name)

        # Build complete environment with PATH including virtualenv
        env = self._build_app_env(app)

        try:
            result = run_command(
                cmd_to_run,
                cwd=app.src_path,
                env=env,
                text=True,
                timeout=300,  # 5 minute timeout for user commands
                input=stdin_data,
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

    def _build_app_env(self, app) -> dict[str, str]:
        """Build complete environment for running commands in app context.

        This mirrors the environment setup in spawn.py make_env() to ensure
        commands have access to the virtualenv, proper PATH, etc.
        """
        virtualenv_path = app.virtualenv_path

        # Start with system PATH, prepend virtualenv bin
        system_path = os.environ.get("PATH", "/usr/bin:/bin")
        venv_bin = virtualenv_path / "bin"

        env = {
            "APP": app.name,
            "HOME": str(HOP3_ROOT),
            "USER": HOP3_USER,
            "PATH": f"{venv_bin}:{system_path}",
            "PWD": str(app.src_path),
            "VIRTUAL_ENV": str(virtualenv_path),
        }

        # Add app's stored environment variables
        env.update(dict(app.get_runtime_env().items()))

        return env


# --- SBOM Command ---


@register
@dataclass(frozen=True)
class SbomCmd(Command):
    """Generate a Software Bill of Materials (SBOM) for an app."""

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("app", "sbom")

    def call(self, *args):
        if not args:
            msg = "Usage: hop app sbom <app_name>"
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
            pip_cmd = [str(venv / "bin" / "pip"), "list", "--format=freeze"]
            result = subprocess.run(pip_cmd, check=True, capture_output=True, text=True)
            req_file.write_text(result.stdout)

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
