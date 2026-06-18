# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for configuration management."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from hop3.config import HopConfig
from hop3.core.identifiers import InvalidIdentifierError, validate_hostname_list
from hop3.deployers.addon_provisioning import addon_var_names
from hop3.lib.args import parse_cli_args
from hop3.lib.registry import register
from hop3.project.procfile import Procfile

from ._base import Command
from ._helpers import (
    check_hostname_conflict,
    get_app,
    parse_key_value_settings,
    redact_sensitive_value,
    set_env_var,
    unset_env_var,
)
from ._response import code, error, success, summary, table, text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from hop3.orm import App


@register
class EnvCmd(Command):
    """Manage application environment variables.

    `config` is a back-compat alias (e.g. `hop3 config set ...` still works).

    Examples:
        hop3 env show --app myapp          # List env vars
        hop3 env set --app myapp KEY=VAL   # Set an env var
        hop3 env unset --app myapp KEY     # Remove an env var
    """

    name: ClassVar[tuple[str, ...]] = ("env",)
    aliases: ClassVar[list[tuple[str, ...]]] = [("config",)]


@register
@dataclass(frozen=True)
class ShowCmd(Command):
    """Show all environment variables for an app.

    Secrets are redacted by default (password-like vars and credentials
    embedded in connection-string URLs). Pass --show-secrets to reveal them.

    Flags:
        --show-secrets  Show full values, including secrets
        --show-compose  Show the generated Docker Compose file (for container apps)
        --sources       Add a column showing each var's source (addon vs config)


    Examples:
        hop3 env show --app myapp                 # List env vars (secrets redacted)
        hop3 env show --app myapp --show-secrets  # Reveal full values
        hop3 env show --app myapp --sources       # Show where each var came from
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("env", "show")
    aliases: ClassVar[list[tuple[str, ...]]] = [("config", "show")]
    # Argument specification for declarative parsing
    _arg_spec: ClassVar[dict] = {
        "app": {"type": str},  # --app <name>
        "show_compose": {"flag": True, "default": False},
        "show_secrets": {"flag": True, "default": False},
        "sources": {"flag": True, "default": False},
        "_args": {"remaining": True},  # Catches positional args
    }

    def call(self, *args):
        parsed = parse_cli_args(args, self._arg_spec)
        app_name = parsed.get("app")
        show_compose = parsed["show_compose"]
        show_secrets = parsed["show_secrets"]

        if not app_name:
            return [
                text(
                    "Usage: hop3 env show [--app <app-name>] [--show-secrets] [--show-compose]\n\n"
                    "Flags:\n"
                    "  --show-secrets  Show full values, including secrets\n"
                    "  --show-compose  Show the generated Docker Compose file\n\n"
                    "Example:\n"
                    "  hop3 env show --app myapp\n"
                    "  hop3 env show --app myapp --show-secrets"
                )
            ]

        app = get_app(self.db_session, app_name)

        # If --show-compose flag is set, show the Docker Compose file
        if show_compose:
            return self._show_compose_file(app)

        env = app.get_runtime_env()
        if not env:
            return [text(f"No configuration set for '{app_name}'.")]

        def _value(key: str, val: str) -> str:
            return val if show_secrets else redact_sensitive_value(key, val)

        if parsed["sources"]:
            # 3-column view: which vars came from an attached addon vs config.
            addon_vars = addon_var_names(app, self.db_session)
            rows = [
                ["addon" if k in addon_vars else "config", k, _value(k, v)]
                for k, v in sorted(env.items())
            ]
            return [
                text(f"Configured environment for '{app_name}':"),
                table(headers=["Source", "Key", "Value"], rows=rows),
            ]

        rows = [[k, _value(k, v)] for k, v in sorted(env.items())]
        return [
            text(f"Configured environment for '{app_name}':"),
            table(headers=["Key", "Value"], rows=rows),
            text(
                "\nNote: These are configured values. Use 'env live' to see actual running values."
            ),
        ]

    def _show_compose_file(self, app: App) -> list[dict]:
        """Show the generated Docker Compose file for the app.

        Args:
            app: The application

        Returns:
            List of output messages
        """
        # Look for the generated compose file
        compose_file = app.src_path / ".hop3-compose.yml"

        if not compose_file.exists():
            # Check for user-provided compose file
            user_compose = app.src_path / "docker-compose.yml"
            if user_compose.exists():
                compose_file = user_compose
            else:
                user_compose_yaml = app.src_path / "docker-compose.yaml"
                if user_compose_yaml.exists():
                    compose_file = user_compose_yaml
                else:
                    return [
                        text(f"No Docker Compose file found for app '{app.name}'."),
                        text("This app may not use container-based deployment."),
                    ]

        try:
            content = compose_file.read_text()
            return [
                text(f"==> {compose_file.name} <=="),
                code(content, lang="yaml"),
            ]
        except Exception as e:
            return [error(f"Error reading compose file: {e}")]


@register
@dataclass(frozen=True)
class GetCmd(Command):
    """Get a specific environment variable.

    Examples:
        hop3 env get --app myapp KEY   # Show one env var's value
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("env", "get")
    aliases: ClassVar[list[tuple[str, ...]]] = [("config", "get")]
    # Argument specification for declarative parsing
    _arg_spec: ClassVar[dict] = {
        "app": {"type": str},  # --app <name>
        "_args": {"remaining": True},  # Catches positional args
    }

    def call(self, *args):
        parsed = parse_cli_args(args, self._arg_spec)
        remaining = parsed["_args"]

        app_name = parsed.get("app")
        setting = remaining[0] if remaining else None

        if not app_name or not setting:
            return [
                text(
                    "Usage: hop3 env get [--app <app-name>] <key>\n\n"
                    "Example:\n"
                    "  hop3 env get --app myapp DATABASE_URL"
                )
            ]

        app = get_app(self.db_session, app_name)
        env = app.get_runtime_env()
        if setting in env:
            return [text(env[setting])]
        return [text(f"Setting '{setting}' not found.")]


@register
@dataclass(frozen=True)
class LiveCmd(Command):
    """Show actual live environment from running app.

    Unlike `env show` which shows database values, this inspects the
    running process/container to show what's actually in effect.

    Secrets are redacted by default; pass --show-secrets to reveal them.

    Usage: hop3 env live [--app <app>] [--show-secrets]


    Examples:
        hop3 env live --app myapp                 # Live runtime environment (secrets redacted)
        hop3 env live --app myapp --show-secrets  # Reveal full values
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("env", "live")
    aliases: ClassVar[list[tuple[str, ...]]] = [("config", "live")]
    # Argument specification for declarative parsing
    _arg_spec: ClassVar[dict] = {
        "app": {"type": str},  # --app <name>
        "show_secrets": {"flag": True, "default": False},
        "_args": {"remaining": True},  # Catches positional args
    }

    def call(self, *args):
        parsed = parse_cli_args(args, self._arg_spec)
        app_name = parsed.get("app")
        show_secrets = parsed["show_secrets"]

        if not app_name:
            return [
                text(
                    "Usage: hop3 env live [--app <app-name>] [--show-secrets]\n\n"
                    "Shows the actual environment variables from the running app.\n"
                    "Use 'env show' to see configured (pending) values."
                )
            ]

        app = get_app(self.db_session, app_name)

        # Read the live environment based on runtime type. Fail loud if we
        # can't: returning stored DB values mislabeled as "live" is exactly the
        # silent fallback this command exists to avoid. Use 'config show' for
        # the configured values.
        if app.runtime == "docker-compose":
            live_env = self._get_docker_env(app_name)
        elif app.runtime == "uwsgi":
            live_env = self._get_uwsgi_env(app)
        else:
            msg = (
                f"Can't read live environment for '{app_name}': unsupported or "
                f"undeployed runtime '{app.runtime or 'none'}'. "
                f"Use 'hop3 env show --app {app_name}' for configured values."
            )
            raise ValueError(msg)

        if not live_env:
            msg = (
                f"Can't inspect the live environment of '{app_name}' "
                f"(runtime: {app.runtime}): the app appears stopped or not "
                f"deployed. Check 'hop3 app status --app {app_name}', or use "
                f"'hop3 env show --app {app_name}' for the configured values."
            )
            raise ValueError(msg)

        rows = [
            [k, v if show_secrets else redact_sensitive_value(k, v)]
            for k, v in sorted(live_env.items())
        ]
        return [
            text(f"Live environment for '{app_name}' (runtime: {app.runtime}):"),
            table(headers=["Key", "Value"], rows=rows),
        ]

    def _get_docker_env(self, app_name: str) -> dict | None:
        """Get environment from running Docker container."""
        container_name = f"hop3-{app_name}"
        try:
            result = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    "{{range .Config.Env}}{{println .}}{{end}}",
                    container_name,
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                live_env = {}
                for line in result.stdout.strip().split("\n"):
                    if "=" in line:
                        key, value = line.split("=", 1)
                        live_env[key] = value
                return live_env or None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

    def _get_uwsgi_env(self, app) -> dict | None:
        """Get environment from running uWSGI process."""
        cfg = HopConfig.get_instance()
        pid_file = Path(cfg.UWSGI_ENABLED) / f"{app.name}.pid"

        if not pid_file.exists():
            return None

        try:
            pid = int(pid_file.read_text().strip())
            # Read environment from /proc/<pid>/environ
            environ_path = f"/proc/{pid}/environ"
            result = subprocess.run(
                ["cat", environ_path],
                capture_output=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0 and result.stdout:
                live_env = {}
                # /proc/pid/environ uses null bytes as separators
                for entry in result.stdout.split(b"\x00"):
                    if b"=" in entry:
                        key, value = entry.decode("utf-8", errors="replace").split(
                            "=", 1
                        )
                        live_env[key] = value
                return live_env or None
        except (FileNotFoundError, ValueError, subprocess.TimeoutExpired, OSError):
            pass
        return None


@register
@dataclass(frozen=True)
class SetCmd(Command):
    """Set environment variables for an app.

    Usage: hop3 env set [--app <app>] KEY=VALUE [KEY2=VALUE2 ...]

    Examples:
        hop3 env set --app myapp DEBUG=true
        hop3 env set --app myapp DATABASE_URL=postgres://... REDIS_URL=redis://...
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("env", "set")
    aliases: ClassVar[list[tuple[str, ...]]] = [("config", "set")]
    # Argument specification for declarative parsing
    _arg_spec: ClassVar[dict] = {
        "app": {"type": str},  # --app <name>
        "_args": {"remaining": True},  # Catches positional args
    }

    def call(self, *args):
        parsed = parse_cli_args(args, self._arg_spec)
        remaining = parsed["_args"]

        app_name = parsed.get("app")
        settings = remaining

        if not app_name or not settings:
            return [
                text(
                    "Usage: hop3 env set [--app <app>] KEY=VALUE [KEY2=VALUE2 ...]\n\n"
                    "Example: hop3 env set --app myapp DEBUG=true"
                )
            ]

        app = get_app(self.db_session, app_name)

        # Parse and validate settings
        key_values, errors = parse_key_value_settings(settings)

        # Validate HOST_NAME syntax and uniqueness
        if "HOST_NAME" in key_values:
            hostname = key_values["HOST_NAME"]
            if hostname and hostname != "_":
                try:
                    parsed_hosts = validate_hostname_list(hostname)
                except InvalidIdentifierError as e:
                    errors.append(str(e))
                    del key_values["HOST_NAME"]
                else:
                    conflict = check_hostname_conflict(
                        self.db_session, app_name, parsed_hosts
                    )
                    if conflict:
                        other_app, other_host = conflict
                        errors.append(
                            f"Hostname '{other_host}' is already used by app "
                            f"'{other_app}'"
                        )
                        del key_values["HOST_NAME"]

        if errors:
            return [error("\n".join(errors))]

        # Apply changes
        changes = [set_env_var(app, key, value) for key, value in key_values.items()]

        # Commit changes to database
        self.db_session.commit()

        result = [text(f"Updated configuration for '{app_name}':")]
        for change in changes:
            result.append(text(f"  • {change}"))

        # Determine appropriate action message based on what was changed
        # Infrastructure variables require full redeploy (affects nginx/proxy config)
        infra_vars = {"HOST_NAME", "HTTPS_ONLY", "AUTO_RESTART", "NGINX_SERVER_NAME"}
        changed_infra = set(key_values.keys()) & infra_vars

        if changed_infra:
            result.append(
                text(
                    f"\nNote: {', '.join(sorted(changed_infra))} changed. "
                    f"Run 'hop3 deploy --app {app_name}' to apply (affects proxy config)."
                )
            )
        else:
            result.append(
                text(
                    f"\nNote: Run 'hop3 app restart --app {app_name}' to apply changes."
                )
            )

        # Summary line per ADR 036 D19c: one-line state-change report.
        keys_set = ", ".join(sorted(key_values.keys()))
        result.append(summary(f"set {keys_set} on {app_name}."))
        return result


@register
@dataclass(frozen=True)
class UnsetCmd(Command):
    """Unset environment variables for an app.

    Usage: hop3 env unset [--app <app>] KEY [KEY2 ...]

    Examples:
        hop3 env unset --app myapp DEBUG
        hop3 env unset --app myapp DATABASE_URL REDIS_URL
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("env", "unset")
    aliases: ClassVar[list[tuple[str, ...]]] = [("config", "unset")]
    # Argument specification for declarative parsing
    _arg_spec: ClassVar[dict] = {
        "app": {"type": str},  # --app <name>
        "_args": {"remaining": True},  # Catches positional args
    }

    def call(self, *args):
        parsed = parse_cli_args(args, self._arg_spec)
        remaining = parsed["_args"]

        app_name = parsed.get("app")
        keys = remaining

        if not app_name or not keys:
            return [
                text(
                    "Usage: hop3 env unset [--app <app>] KEY [KEY2 ...]\n\n"
                    "Example: hop3 env unset --app myapp DEBUG"
                )
            ]

        app = get_app(self.db_session, app_name)

        # Remove specified variables
        removed = []
        not_found = []
        for raw_key in keys:
            key = raw_key.strip()
            if not key:
                continue

            if unset_env_var(app, key):
                removed.append(key)
            else:
                not_found.append(key)

        # Commit changes to database
        self.db_session.commit()

        result = []
        if removed:
            result.append(text(f"Removed configuration from '{app_name}':"))
            for key in removed:
                result.append(text(f"  • {key}"))

        if not_found:
            result.append(text("\nNot found:"))
            for key in not_found:
                result.append(text(f"  • {key}"))

        if removed:
            result.append(
                text(
                    "\nNote: Run 'hop3 app restart --app <app>' to apply changes to running app."
                )
            )
            result.append(summary(f"unset {', '.join(removed)} on {app_name}."))

        return result


@register
class MigrateCmd(Command):
    """Migrate configuration from other PaaS formats to hop3.toml.

    This is a one-off project-scaffolding task (Procfile → hop3.toml format
    conversion), so it lives under `app`, not env-var management.

    Examples:
        hop3 app migrate procfile /path/to/app    # Convert Procfile to hop3.toml
        hop3 app migrate procfile /path/to/app --dry-run
    """

    name: ClassVar[tuple[str, ...]] = ("app", "migrate")
    aliases: ClassVar[list[tuple[str, ...]]] = [
        ("env", "migrate"),
        ("config", "migrate"),
    ]

    def call(  # noqa: PLR0911 — sequential precondition cascade (usage, format, dir-exists, Procfile-exists, parse, dry-run, output-exists, success) where each return carries its own user-facing message; a state-machine refactor here trades clarity for a metric.
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
                text(
                    "Usage: hop3 app migrate <from-format> <app-dir> [--dry-run] [--backup]\n\n"
                    "Supported formats:\n"
                    "  procfile    Convert Procfile to hop3.toml\n\n"
                    "Example:\n"
                    "  hop3 app migrate procfile /path/to/app"
                )
            ]

        if from_format.lower() != "procfile":
            return [
                error(
                    f"Unsupported format: {from_format}. Currently only 'procfile' is supported."
                )
            ]

        app_path = Path(app_dir)
        if not app_path.exists():
            return [error(f"Directory not found: {app_dir}")]

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
            return [error(f"Procfile not found in {app_dir}")]

        # Parse the Procfile
        try:
            procfile = Procfile.from_file(procfile_path)
        except Exception as e:
            return [error(f"Failed to parse Procfile: {e}")]

        # Generate hop3.toml content
        toml_content = self._generate_hop3_toml(procfile)

        if dry_run:
            return [
                text("Generated hop3.toml content (dry-run):"),
                text(""),
                text(toml_content),
            ]

        # Create backup if requested
        backup_path = None
        if backup:
            backup_path = procfile_path.with_suffix(".bak")
            backup_path.write_text(procfile_path.read_text())

        # Write hop3.toml
        output_path = procfile_path.parent / "hop3.toml"
        if output_path.exists():
            return [
                error(
                    f"hop3.toml already exists at {output_path}. Remove it first or use --force."
                )
            ]

        output_path.write_text(toml_content)

        return [
            success("Successfully converted Procfile to hop3.toml"),
            text(f"Created: {output_path}"),
            text(f"Backup: {backup_path}" if backup else ""),
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

        # Build section
        if "prebuild" in workers:
            lines.append("[build]")
            lines.append(f'before-build = "{workers["prebuild"]}"')
            lines.append("")

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
