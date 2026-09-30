# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Miscellaneous CLI commands."""

from __future__ import annotations

import shlex
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from importlib.metadata import version as get_version
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from hop3 import config as c
from hop3.core.roles import Role
from hop3.deployers import do_deploy
from hop3.lib.args import pop_app_flag, reject_extra_args
from hop3.lib.logging import server_log
from hop3.lib.registry import lookup, register
from hop3.lib.util import (
    CommandError,
    stream_command,
)
from hop3.project.procfile import parse_procfile
from hop3.run.app_env import build_app_env, load_artifact, make_runtime_dirs
from hop3.server.streaming import create_stream

from ._base import Command, NamespaceCommand
from ._errors import command_context
from ._helpers import get_app
from ._response import error, stream, table, text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# --- Version Command ---


@register
@dataclass(frozen=True)
class VersionCmd(Command):
    """
    Show version information.

    Examples:
        hop3 version                   # Show CLI and server versions
    """

    name: ClassVar[tuple[str, ...]] = ("version",)
    requires_auth: ClassVar[bool] = False  # Public command

    def call(self, *args: str, **kwargs: object) -> list[dict]:
        try:
            server_version = get_version("hop3-server")
        except Exception:
            server_version = "unknown"

        return [text(f"hop3-server {server_version}")]


# --- Plugins Command ---


@register
@dataclass(frozen=True)
class PluginCmd(NamespaceCommand):
    """
    Manage plugins.

    Examples:
        hop3 plugin list               # List installed plugins
    """

    name: ClassVar[tuple[str, ...]] = ("plugin",)
    min_role: ClassVar[Role] = Role.VIEWER


@register
@dataclass(frozen=True)
class PluginsCmd(Command):
    """
    List installed plugins and their commands.

    Examples:
        hop3 plugin list               # List installed plugins (alias: 'hop3 plugins')
        hop3 plugins                   # Same via alias
    """

    # Canonical name is `plugin list` per ADR 036 D9 (plural `plugins` is the
    # alias, resolved client-side in `hop3_cli.core.aliases.CORE_ALIASES`).
    name: ClassVar[tuple[str, ...]] = ("plugin", "list")
    min_role: ClassVar[Role] = Role.VIEWER

    def call(self, *args: str, **kwargs: object) -> list[dict]:
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
    """
    Show process count for an application.

    Usage: hop3 ps [--app <app>]

    Examples:
        hop3 ps --app myapp            # Show processes for myapp
        hop3 ps                        # app from the current project/context
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("ps",)
    min_role: ClassVar[Role] = Role.VIEWER

    def call(self, *args: str, **kwargs: object) -> list[dict]:
        app_name, rest = pop_app_flag(args)
        reject_extra_args(rest)  # `ps` takes no positionals (audit C9)

        if app_name is None:
            raise self.usage_error()
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
    """
    Set the process count (e.g., hop3 ps scale --app <app> web=2 worker=1).

    Usage: hop3 ps scale [--app <app>] <type>=<count> ...

    Examples:
        hop3 ps scale --app myapp web=2   # Run 2 web workers
        hop3 ps scale --app myapp web=2 worker=1
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("ps", "scale")
    min_role: ClassVar[Role] = Role.DEPLOYER

    def call(self, *args: str, **kwargs: object) -> list[dict]:
        app_name, rest = pop_app_flag(args)

        if app_name is None or not rest:
            raise self.usage_error()

        settings = rest
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
    """
    Run a one-off command in the context of an application.

    Usage: hop3 app run [--app <app>] <command> [args...] [--input <data>]

    `hop3 run ...` works as a top-level alias. The app is read from the
    `--app`/`-a` flag; everything that remains is the command line to execute.

    Options:
        --input <data>: Data to send to the command's stdin (non-interactive).

    Examples:
        hop3 app run --app myapp flask db upgrade
        hop3 run --app myapp flask users change_password user@example.com --input "newpw"
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("app", "run")
    min_role: ClassVar[Role] = Role.DEPLOYER
    aliases: ClassVar[list[tuple[str, ...]]] = [("run",)]

    def call(self, *args: str, **kwargs: object) -> list[dict]:
        # Resolve the app from --app. `run` is special: everything that remains
        # after the flag is the command line to execute.
        app_name, rest = pop_app_flag(args)
        args_list = rest

        if app_name is None or not args_list:
            raise self.usage_error()

        # Parse --input option
        stdin_data = None
        if "--input" in args_list:
            idx = args_list.index("--input")
            if idx + 1 < len(args_list):
                stdin_data = args_list[idx + 1] + "\n"  # Add newline for input
                args_list = args_list[:idx] + args_list[idx + 2 :]
            else:
                return [error("--input requires a value")]

        cmd_to_run = args_list
        app = get_app(self.db_session, app_name)

        # Everything the command needs is read here, in the request thread.
        # The RPC session is committed and closed the moment this returns the
        # stream item, and sessions are not thread-safe — so the worker below
        # closes over plain values, never over `app` or the session.
        cwd = app.src_path
        make_runtime_dirs(app)
        env = build_app_env(app, load_artifact(app))
        return [run_command_streaming(app.name, cmd_to_run, cwd, env, stdin_data)]


def run_command_streaming(
    app_name: str,
    cmd: list[str],
    cwd: Path,
    env: dict[str, str],
    stdin_data: str | None,
) -> dict:
    """
    Run a one-off command in a worker thread, streaming its output over SSE.

    This used to run inline with a five-minute timeout and return the captured
    output at the end, which failed the two things a one-off command is for.
    A maintenance job that legitimately takes longer was killed mid-work and
    reported as a read timeout, naming a localhost port rather than the job;
    and until it finished there was nothing to look at, so a job that was
    working and a job that was wedged looked identical.

    It is not put on the build queue: that queue exists to bound concurrent
    *builds*, and making an operator's command wait behind a deploy would be a
    second way to look wedged.
    """
    log_stream = create_stream(app_name)
    cmd_str = shlex.join(cmd)

    def run() -> None:
        printed = False

        def on_line(line: str) -> None:
            nonlocal printed
            printed = True
            log_stream.write(line)

        try:
            log_stream.write(f"$ {cmd_str}", fg="blue")
            returncode = stream_command(
                cmd,
                on_line=on_line,
                cwd=cwd,
                env=env,
                stdin_data=stdin_data,
            )
        except CommandError as e:
            log_stream.finish(success=False, error_message=e.message)
            return
        except Exception as e:
            # Top of a thread: an exception escaping here is swallowed by
            # `threading`, and the client waits on a stream that will never
            # complete. Anything unexpected (a broken pipe writing stdin, a
            # permission error on cwd) has to end the stream saying so. Same
            # shape as the deploy worker in commands/_deploy.py.
            server_log.exception("run command raised", app_name=app_name)
            log_stream.finish(success=False, error_message=str(e))
            return

        if returncode == 0:
            log_stream.finish(success=True, success_message="Command completed")
            return

        if not printed:
            # Never a silent bare exit code: say that nothing was printed, so
            # the operator knows the silence is the command's and not ours.
            log_stream.write(
                "(the command produced no output — it likely failed before "
                "printing anything)",
                fg="yellow",
            )

        server_log.warning(
            "run command failed",
            app_name=app_name,
            cmd=cmd_str,
            returncode=returncode,
        )
        log_stream.finish(
            success=False,
            error_message=f"Command failed with exit code {returncode}",
        )

    threading.Thread(target=run, daemon=True, name=f"run-{app_name}").start()
    return stream(log_stream.stream_id)


@register
@dataclass(frozen=True)
class AppShellCmd(Command):
    """
    Open an interactive shell in an app's runtime context.

    Usage: hop3 app shell [--app <app>]

    `hop3 ssh` is a top-level alias. The shell starts in the app's working
    tree with the environment its processes see (addon URLs, the [env] block,
    the toolchain on PATH), as the hop3 user. It is `hop3 run` with a terminal
    attached: REPLs, `tail -f`, pagers and debuggers work. Exit the shell to
    end the session; its exit status is the command's.

    This command travels over SSH, not the RPC API: the CLI opens `ssh -t` to
    the configured ssh:// server and hands the terminal to the server-side
    `hop3-server app-shell`. It needs an ssh:// server; an http:// server
    cannot carry a terminal.

    Examples:
        hop3 app shell --app myapp
        hop3 ssh                      # app from context
    """

    name: ClassVar[tuple[str, ...]] = ("app", "shell")
    min_role: ClassVar[Role] = Role.DEPLOYER

    def call(self, *args: str, **kwargs: object) -> list[dict]:
        # The CLI runs this command itself, over SSH; only a client that does
        # not know it (older than the server) sends it here. Say so loudly
        # rather than pretend a terminal can be opened over RPC.
        return [
            error(
                "`hop3 app shell` opens a terminal over SSH; the hop3 CLI runs it "
                "itself and never sends it here. This client sent it over RPC: "
                "upgrade hop3-cli and connect through an ssh:// server."
            )
        ]


# --- SBOM Command ---


@register
@dataclass(frozen=True)
class SbomCmd(Command):
    """
    Generate a Software Bill of Materials (SBOM) for an application.

    Usage: hop3 app sbom [--app <app>]

    Examples:
        hop3 app sbom --app myapp      # Generate an SBOM for myapp
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("app", "sbom")
    min_role: ClassVar[Role] = Role.VIEWER

    def call(self, *args: str, **kwargs: object) -> list[dict]:
        app_name, rest = pop_app_flag(args)
        reject_extra_args(rest)  # `app sbom` takes no positionals (audit C9)

        if app_name is None:
            raise self.usage_error()
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
