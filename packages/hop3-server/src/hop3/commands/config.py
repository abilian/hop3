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
from hop3.lib.args import parse_cli_args
from hop3.lib.registry import register
from hop3.orm import App, AppRepository
from hop3.project.procfile import Procfile

from ._base import Command
from ._helpers import get_app, parse_key_value_settings, set_env_var, unset_env_var
from ._response import code, error, success, summary, table, text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@register
class ConfigCmd(Command):
    """Manage application configuration and environment variables.

    Examples:
        hop3 config show myapp         # List env vars
        hop3 config set myapp KEY=VAL  # Set an env var
        hop3 config unset myapp KEY    # Remove an env var
    """

    name: ClassVar[tuple[str, ...]] = ("config",)


@register
@dataclass(frozen=True)
class ShowCmd(Command):
    """Show all configuration variables for an app.

    Flags:
        --show-compose  Show the generated Docker Compose file (for container apps)


    Examples:
        hop3 config show myapp         # List all env vars for myapp
        hop3 env myapp                 # Same via cross-platform alias
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("config", "show")
    # Argument specification for declarative parsing
    _arg_spec: ClassVar[dict] = {
        "app": {"type": str},  # --app <name>
        "show_compose": {"flag": True, "default": False},
        "_args": {"remaining": True},  # Catches positional args
    }

    def call(self, *args):
        parsed = parse_cli_args(args, self._arg_spec)
        # Support both: config show myapp OR config show --app myapp
        app_name = parsed.get("app") or (
            parsed["_args"][0] if parsed["_args"] else None
        )
        show_compose = parsed["show_compose"]

        if not app_name:
            return [
                text(
                    "Usage: hop3 config show <app-name> [--show-compose]\n"
                    "   or: hop3 config show --app <app-name> [--show-compose]\n\n"
                    "Flags:\n"
                    "  --show-compose  Show the generated Docker Compose file\n\n"
                    "Example:\n"
                    "  hop3 config show myapp\n"
                    "  hop3 config show myapp --show-compose"
                )
            ]

        app = get_app(self.db_session, app_name)

        # If --show-compose flag is set, show the Docker Compose file
        if show_compose:
            return self._show_compose_file(app)

        env = app.get_runtime_env()
        if not env:
            return [text(f"No configuration set for '{app_name}'.")]

        rows = [[k, v] for k, v in sorted(env.items())]
        return [
            text(f"Configured environment for '{app_name}':"),
            table(headers=["Key", "Value"], rows=rows),
            text(
                "\nNote: These are configured values. Use 'config live' to see actual running values."
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
    """Get a specific configuration variable.

    Examples:
        hop3 config get myapp KEY      # Show one env var's value
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("config", "get")
    # Argument specification for declarative parsing
    _arg_spec: ClassVar[dict] = {
        "app": {"type": str},  # --app <name>
        "_args": {"remaining": True},  # Catches positional args
    }

    def call(self, *args):
        parsed = parse_cli_args(args, self._arg_spec)
        remaining = parsed["_args"]

        # Support both: config get myapp KEY OR config get --app myapp KEY
        if parsed.get("app"):
            app_name = parsed["app"]
            setting = remaining[0] if remaining else None
        else:
            app_name = remaining[0] if len(remaining) > 0 else None
            setting = remaining[1] if len(remaining) > 1 else None

        if not app_name or not setting:
            return [
                text(
                    "Usage: hop3 config get <app-name> <key>\n"
                    "   or: hop3 config get --app <app-name> <key>\n\n"
                    "Example:\n"
                    "  hop3 config get myapp DATABASE_URL"
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

    Unlike config show which shows database values, this inspects
    the running process/container to show what's actually in effect.

    Usage: hop config live <app> or hop config live --app <app>


    Examples:
        hop3 config live myapp         # Show the live runtime environment as seen by the app
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("config", "live")
    # Argument specification for declarative parsing
    _arg_spec: ClassVar[dict] = {
        "app": {"type": str},  # --app <name>
        "_args": {"remaining": True},  # Catches positional args
    }

    def call(self, *args):
        parsed = parse_cli_args(args, self._arg_spec)
        # Support both: config live myapp OR config live --app myapp
        app_name = parsed.get("app") or (
            parsed["_args"][0] if parsed["_args"] else None
        )

        if not app_name:
            return [
                text(
                    "Usage: hop3 config live <app-name>\n"
                    "   or: hop3 config live --app <app-name>\n\n"
                    "Shows the actual environment variables from the running app.\n"
                    "Use 'config show' to see configured (pending) values."
                )
            ]

        app = get_app(self.db_session, app_name)

        # Try to get live environment based on runtime type
        if app.runtime == "docker-compose":
            live_env = self._get_docker_env(app_name)
        elif app.runtime == "uwsgi":
            live_env = self._get_uwsgi_env(app)
        else:
            live_env = None

        if live_env:
            rows = [[k, v] for k, v in sorted(live_env.items())]
            return [
                text(f"Live environment for '{app_name}' (runtime: {app.runtime}):"),
                table(headers=["Key", "Value"], rows=rows),
            ]

        # Fallback: show database values with warning
        db_env = app.get_runtime_env()
        if not db_env:
            return [text(f"App '{app_name}' is not deployed or has no configuration.")]

        return [
            text(f"Could not inspect running {app.runtime} app '{app_name}'."),
            text("Showing configured values (may not match live environment):"),
            table(
                headers=["Key", "Value"],
                rows=[[k, v] for k, v in sorted(db_env.items())],
            ),
            text("\nTip: Run 'hop deploy' to ensure live environment matches config."),
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

    Usage: hop config set <app> KEY=VALUE [KEY2=VALUE2 ...]
       or: hop config set --app <app> KEY=VALUE [KEY2=VALUE2 ...]

    Examples:
        hop config set myapp DEBUG=true
        hop config set --app myapp DATABASE_URL=postgres://... REDIS_URL=redis://...
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("config", "set")
    # Argument specification for declarative parsing
    _arg_spec: ClassVar[dict] = {
        "app": {"type": str},  # --app <name>
        "_args": {"remaining": True},  # Catches positional args
    }

    def call(self, *args):
        parsed = parse_cli_args(args, self._arg_spec)
        remaining = parsed["_args"]

        # Support both: config set myapp K=V OR config set --app myapp K=V
        if parsed.get("app"):
            app_name = parsed["app"]
            settings = remaining
        else:
            app_name = remaining[0] if remaining else None
            settings = remaining[1:] if len(remaining) > 1 else []

        if not app_name or not settings:
            return [
                text(
                    "Usage: hop config set <app> KEY=VALUE [KEY2=VALUE2 ...]\n"
                    "   or: hop config set --app <app> KEY=VALUE [KEY2=VALUE2 ...]\n\n"
                    "Example: hop config set myapp DEBUG=true"
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
                    validate_hostname_list(hostname)
                except InvalidIdentifierError as e:
                    errors.append(str(e))
                    del key_values["HOST_NAME"]
                else:
                    conflict = self._check_hostname_conflict(app_name, hostname)
                    if conflict:
                        errors.append(
                            f"Hostname '{hostname}' is already used by app '{conflict}'"
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
                    f"Run 'hop deploy {app_name}' to apply (affects proxy config)."
                )
            )
        else:
            result.append(
                text(f"\nNote: Run 'hop app restart {app_name}' to apply changes.")
            )

        # Summary line per ADR 036 D19c: one-line state-change report.
        keys_set = ", ".join(sorted(key_values.keys()))
        result.append(summary(f"set {keys_set} on {app_name}."))
        return result

    def _check_hostname_conflict(self, current_app: str, hostname: str) -> str | None:
        """Check if a hostname is already used by another app.

        Args:
            current_app: Name of the current app (to exclude from check)
            hostname: Hostname to check

        Returns:
            Name of the conflicting app, or None if no conflict.
        """
        # Handle comma-separated hostnames (check each one)
        hostnames_to_check = [h.strip() for h in hostname.split(",") if h.strip()]

        app_repo = AppRepository(session=self.db_session)
        all_apps = app_repo.list()

        for app in all_apps:
            if app.name == current_app:
                continue

            # Get the app's current HOST_NAME
            for env_var in app.env_vars:
                if env_var.name == "HOST_NAME" and env_var.value:
                    existing_hostnames = [
                        h.strip() for h in env_var.value.split(",") if h.strip()
                    ]
                    # Check for any overlap
                    for new_hostname in hostnames_to_check:
                        if new_hostname in existing_hostnames:
                            return app.name

        return None


@register
@dataclass(frozen=True)
class UnsetCmd(Command):
    """Unset environment variables for an app.

    Usage: hop config unset <app> KEY [KEY2 ...]
       or: hop config unset --app <app> KEY [KEY2 ...]

    Examples:
        hop config unset myapp DEBUG
        hop config unset --app myapp DATABASE_URL REDIS_URL
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("config", "unset")
    # Argument specification for declarative parsing
    _arg_spec: ClassVar[dict] = {
        "app": {"type": str},  # --app <name>
        "_args": {"remaining": True},  # Catches positional args
    }

    def call(self, *args):
        parsed = parse_cli_args(args, self._arg_spec)
        remaining = parsed["_args"]

        # Support both: config unset myapp KEY OR config unset --app myapp KEY
        if parsed.get("app"):
            app_name = parsed["app"]
            keys = remaining
        else:
            app_name = remaining[0] if remaining else None
            keys = remaining[1:] if len(remaining) > 1 else []

        if not app_name or not keys:
            return [
                text(
                    "Usage: hop config unset <app> KEY [KEY2 ...]\n"
                    "   or: hop config unset --app <app> KEY [KEY2 ...]\n\n"
                    "Example: hop config unset myapp DEBUG"
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
                    "\nNote: Run 'hop app restart <app>' to apply changes to running app."
                )
            )
            result.append(summary(f"unset {', '.join(removed)} on {app_name}."))

        return result


@register
class MigrateCmd(Command):
    """Migrate configuration from other PaaS formats to hop3.toml.

    Examples:
        hop3 config migrate procfile /path/to/app    # Convert Procfile to hop3.toml
        hop3 config migrate procfile /path/to/app --dry-run
    """

    name: ClassVar[tuple[str, ...]] = ("config", "migrate")

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
                text(
                    "Usage: hop config migrate <from-format> <app-dir> [--dry-run] [--backup]\n\n"
                    "Supported formats:\n"
                    "  procfile    Convert Procfile to hop3.toml\n\n"
                    "Example:\n"
                    "  hop config migrate procfile /path/to/app"
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
