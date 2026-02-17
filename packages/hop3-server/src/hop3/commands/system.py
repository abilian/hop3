# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands."""

from __future__ import annotations

import importlib.metadata
import os
import pathlib
import platform
import pwd
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import ClassVar

from hop3.config import HOP3_ROOT
from hop3.core.plugins import get_plugin_manager
from hop3.lib.logging import DEFAULT_LOG_FILE
from hop3.lib.registry import register
from hop3.server.health import (
    check_mysql_health,
    check_postgres_health,
    check_redis_health,
)

from ._base import Command


@register
class SystemCmd(Command):
    """Manage the hop3 system."""

    name: ClassVar[str] = "system"


@register
class CheckCmd(Command):
    """Run comprehensive health checks on the Hop3 server.

    This command verifies that all server components are properly configured
    and operational. Use this to diagnose issues before deploying applications.

    Checks performed:
        - Core services (hop3-server, nginx, uwsgi-hop3)
        - Database addons (PostgreSQL, MySQL) if configured
        - Redis connectivity if installed
        - Filesystem permissions and directories
        - Configuration file validity
        - SSL certificates
        - Disk space

    Usage: hop3 system:check [options]

    Options:
        --verbose, -v    Show detailed output for each check

    Examples:
        hop3 system:check              # Run all health checks
        hop3 system:check --verbose    # Detailed output
    """

    name: ClassVar[str] = "system:check"

    def call(self, *args, **kwargs):
        verbose = "--verbose" in args or "-v" in args

        results = []
        all_passed = True

        # Header
        results.append("Hop3 System Health Check")
        results.append("=" * 50)
        results.append("")

        # 1. Core services
        services_ok, services_output = self._check_services(verbose)
        results.extend(services_output)
        all_passed = all_passed and services_ok

        # 2. Database addons
        db_ok, db_output = self._check_databases(verbose)
        results.extend(db_output)
        all_passed = all_passed and db_ok

        # 3. Filesystem
        fs_ok, fs_output = self._check_filesystem(verbose)
        results.extend(fs_output)
        all_passed = all_passed and fs_ok

        # 4. Configuration
        config_ok, config_output = self._check_configuration(verbose)
        results.extend(config_output)
        all_passed = all_passed and config_ok

        # 5. SSL certificates
        ssl_ok, ssl_output = self._check_ssl(verbose)
        results.extend(ssl_output)
        all_passed = all_passed and ssl_ok

        # 6. Disk space
        disk_ok, disk_output = self._check_disk_space(verbose)
        results.extend(disk_output)
        all_passed = all_passed and disk_ok

        # 7. Docker (if available)
        _docker_ok, docker_output = self._check_docker(verbose)
        results.extend(docker_output)
        # Docker is optional, don't affect overall status

        # Summary
        results.append("")
        results.append("=" * 50)
        if all_passed:
            results.append("✓ All checks passed")
        else:
            results.append("✗ Some checks failed - review output above")

        return [{"t": "text", "text": "\n".join(results)}]

    def _check_services(self, verbose: bool) -> tuple[bool, list[str]]:
        """Check core system services."""
        lines = ["Services", "-" * 30]
        all_ok = True

        services = [
            ("hop3-server", "Hop3 Server"),
            ("nginx", "Nginx"),
            ("uwsgi-hop3", "uWSGI Emperor"),
        ]

        for service_name, display_name in services:
            result = subprocess.run(
                ["systemctl", "is-active", service_name],
                capture_output=True,
                text=True,
                check=False,
            )
            is_active = result.stdout.strip() == "active"

            if is_active:
                lines.append(f"  ✓ {display_name}: running")
            else:
                lines.append(f"  ✗ {display_name}: not running")
                all_ok = False
                if verbose:
                    # Get more details
                    status_result = subprocess.run(
                        ["systemctl", "status", service_name, "--no-pager", "-l"],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    # Show last few lines
                    status_lines = status_result.stdout.strip().split("\n")[-5:]
                    for sl in status_lines:
                        lines.append(f"      {sl}")

        lines.append("")
        return all_ok, lines

    def _check_databases(self, verbose: bool) -> tuple[bool, list[str]]:
        """Check database addon connectivity."""
        lines = ["Database Addons", "-" * 30]
        all_ok = True

        # PostgreSQL
        pg_ok = check_postgres_health()
        if pg_ok:
            lines.append("  ✓ PostgreSQL: OK")
        else:
            lines.append("  ✗ PostgreSQL: connection failed")
            all_ok = False
            if verbose:
                lines.append("      Check POSTGRES_SUPERUSER_PASSWORD in hop3-server.toml")
                lines.append("      Verify PostgreSQL service: systemctl status postgresql")

        # MySQL
        mysql_ok = check_mysql_health()
        if mysql_ok:
            lines.append("  ✓ MySQL: OK")
        else:
            lines.append("  ✗ MySQL: connection failed")
            all_ok = False
            if verbose:
                lines.append("      Check MYSQL_SUPERUSER_PASSWORD in hop3-server.toml")
                lines.append("      Verify MySQL service: systemctl status mysql")

        # Redis
        redis_ok = check_redis_health()
        if redis_ok:
            lines.append("  ✓ Redis: OK")
        else:
            lines.append("  ✗ Redis: not accessible")
            # Redis is optional, don't fail overall check
            if verbose:
                lines.append("      Verify Redis service: systemctl status redis-server")

        lines.append("")
        return all_ok, lines

    def _check_filesystem(self, verbose: bool) -> tuple[bool, list[str]]:
        """Check filesystem permissions and directories."""
        lines = ["Filesystem", "-" * 30]
        all_ok = True

        required_dirs = [
            (HOP3_ROOT, "HOP3_ROOT"),
            (HOP3_ROOT / "apps", "Apps directory"),
            (HOP3_ROOT / "nginx", "Nginx config"),
            (HOP3_ROOT / "uwsgi-available", "uWSGI available"),
            (HOP3_ROOT / "uwsgi-enabled", "uWSGI enabled"),
        ]

        for path, name in required_dirs:
            if path.exists():
                # Check if writable
                if os.access(path, os.W_OK):
                    lines.append(f"  ✓ {name}: exists, writable")
                else:
                    lines.append(f"  ✗ {name}: exists but not writable")
                    all_ok = False
            else:
                lines.append(f"  ✗ {name}: missing ({path})")
                all_ok = False

        # Check hop3 user exists
        try:
            pwd.getpwnam("hop3")
            lines.append("  ✓ hop3 user: exists")
        except KeyError:
            lines.append("  ✗ hop3 user: not found")
            all_ok = False

        lines.append("")
        return all_ok, lines

    def _check_configuration(self, verbose: bool) -> tuple[bool, list[str]]:
        """Check configuration file validity."""
        lines = ["Configuration", "-" * 30]
        all_ok = True

        config_file = HOP3_ROOT / "hop3-server.toml"

        if config_file.exists():
            lines.append(f"  ✓ Config file: {config_file}")

            # Check for required settings
            try:
                content = config_file.read_text()

                if "HOP3_SECRET_KEY" in content:
                    lines.append("  ✓ HOP3_SECRET_KEY: configured")
                else:
                    lines.append("  ✗ HOP3_SECRET_KEY: missing (required for auth)")
                    all_ok = False

                # Check database configs (informational)
                if verbose:
                    has_pg = "POSTGRES_SUPERUSER_PASSWORD" in content
                    has_mysql = "MYSQL_SUPERUSER_PASSWORD" in content
                    lines.append(f"      PostgreSQL addon: {'configured' if has_pg else 'not configured'}")
                    lines.append(f"      MySQL addon: {'configured' if has_mysql else 'not configured'}")

            except Exception as e:
                lines.append(f"  ✗ Config file read error: {e}")
                all_ok = False
        else:
            lines.append(f"  ✗ Config file: missing ({config_file})")
            all_ok = False

        lines.append("")
        return all_ok, lines

    def _check_ssl(self, verbose: bool) -> tuple[bool, list[str]]:
        """Check SSL certificate configuration."""
        lines = ["SSL Certificates", "-" * 30]
        all_ok = True

        ssl_cert = HOP3_ROOT / "nginx" / "ssl" / "hop3.crt"
        ssl_key = HOP3_ROOT / "nginx" / "ssl" / "hop3.key"

        if ssl_cert.exists() and ssl_key.exists():
            lines.append("  ✓ SSL certificate: configured")

            if verbose:
                # Check certificate expiry using openssl
                result = subprocess.run(
                    ["openssl", "x509", "-in", str(ssl_cert), "-noout", "-enddate"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode == 0:
                    lines.append(f"      {result.stdout.strip()}")
        else:
            lines.append("  ⚠ SSL certificate: not configured (using self-signed)")
            # This is a warning, not a failure
            if verbose:
                lines.append("      Apps will work but browsers will show security warnings")

        lines.append("")
        return all_ok, lines

    def _check_disk_space(self, verbose: bool) -> tuple[bool, list[str]]:
        """Check available disk space."""
        lines = ["Disk Space", "-" * 30]
        all_ok = True

        try:
            usage = shutil.disk_usage(HOP3_ROOT)
            total_gb = usage.total / (1024**3)
            used_gb = usage.used / (1024**3)
            free_gb = usage.free / (1024**3)
            percent_used = (usage.used / usage.total) * 100

            if percent_used > 90:
                lines.append(f"  ✗ Disk usage: {percent_used:.1f}% (critical)")
                all_ok = False
            elif percent_used > 80:
                lines.append(f"  ⚠ Disk usage: {percent_used:.1f}% (warning)")
            else:
                lines.append(f"  ✓ Disk usage: {percent_used:.1f}%")

            if verbose:
                lines.append(f"      Total: {total_gb:.1f} GB")
                lines.append(f"      Used: {used_gb:.1f} GB")
                lines.append(f"      Free: {free_gb:.1f} GB")

        except Exception as e:
            lines.append(f"  ✗ Disk check failed: {e}")
            all_ok = False

        lines.append("")
        return all_ok, lines

    def _check_docker(self, verbose: bool) -> tuple[bool, list[str]]:
        """Check Docker availability (optional)."""
        lines = ["Docker (optional)", "-" * 30]

        try:
            result = subprocess.run(
                ["docker", "version", "--format", "{{.Server.Version}}"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                lines.append(f"  ✓ Docker: {version}")

                if verbose:
                    # Check Docker networks
                    net_result = subprocess.run(
                        ["docker", "network", "ls", "-q"],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    net_count = len(net_result.stdout.strip().split("\n"))
                    lines.append(f"      Networks: {net_count}")

                    # Check running containers
                    cont_result = subprocess.run(
                        ["docker", "ps", "-q"],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    containers = cont_result.stdout.strip().split("\n")
                    cont_count = len([c for c in containers if c])
                    lines.append(f"      Running containers: {cont_count}")
            else:
                lines.append("  - Docker: not available")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            lines.append("  - Docker: not installed")

        lines.append("")
        return True, lines  # Docker is optional, always return True


@register
class UptimeCmd(Command):
    """Show host server uptime."""

    name: ClassVar[str] = "system:uptime"

    def call(self, *args):
        result = subprocess.run(
            ["uptime"], capture_output=True, text=True, check=False
        ).stdout
        return [{"t": "text", "text": result}]


@register
class PSCmd(Command):
    """List all server processes."""

    name: ClassVar[str] = "system:ps"

    def call(self, *args):
        result = subprocess.run(
            ["ps", "aux"], capture_output=True, text=True, check=False
        ).stdout
        return [{"t": "text", "text": result}]


@register
class StatusCmd(Command):
    """Show Hop3 system status."""

    name: ClassVar[str] = "system:status"

    def call(self, *args):
        version = importlib.metadata.version("hop3_server")

        return [
            {"t": "text", "text": f"Hop3 version: {version}"},
        ]


@register
class InfoCmd(Command):
    """Show detailed Hop3 system information.

    Use --verbose or -v for more details including loaded plugins.
    """

    name: ClassVar[str] = "system:info"

    def call(self, *args, **kwargs):
        # Parse --verbose/-v from args
        verbose = "--verbose" in args or "-v" in args

        version = importlib.metadata.version("hop3_server")
        python_version = sys.version.split()[0]
        os_info = f"{platform.system()} {platform.release()}"

        lines = [
            "Hop3 System Information",
            "=" * 40,
            f"Version:        {version}",
            f"Python:         {python_version}",
            f"Platform:       {os_info}",
        ]

        # Check Docker availability
        docker_available = self._check_docker()
        lines.append(
            f"Docker:         {'available' if docker_available else 'not available'}"
        )

        if verbose:
            lines.extend(self._get_verbose_info())

        return [{"t": "text", "text": "\n".join(lines)}]

    def _check_docker(self) -> bool:
        """Check if Docker is available."""
        try:
            result = subprocess.run(
                ["docker", "version", "--format", "{{.Server.Version}}"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _get_verbose_info(self) -> list[str]:
        """Get verbose information including plugins."""
        lines = [
            "",
            "Loaded Plugins",
            "-" * 40,
        ]

        pm = get_plugin_manager()

        # Get builders
        builder_classes = []
        for sublist in pm.hook.get_builders():
            builder_classes.extend(sublist)
        if builder_classes:
            lines.append("Builders:")
            for cls in builder_classes:
                lines.append(f"  - {cls.__name__}")
        else:
            lines.append("Builders: (none loaded)")

        # Get deployers
        deployer_classes = []
        for sublist in pm.hook.get_deployers():
            deployer_classes.extend(sublist)
        if deployer_classes:
            lines.append("Deployers:")
            for cls in deployer_classes:
                # Try to get the 'name' attribute if it exists
                name = getattr(cls, "name", cls.__name__)
                lines.append(f"  - {cls.__name__} (runtime: {name})")
        else:
            lines.append("Deployers: (none loaded)")

        # Get toolchains
        toolchain_classes = []
        for sublist in pm.hook.get_toolchains():
            toolchain_classes.extend(sublist)
        if toolchain_classes:
            lines.append("Toolchains:")
            for cls in toolchain_classes:
                lines.append(f"  - {cls.__name__}")
        else:
            lines.append("Toolchains: (none loaded)")

        # Check important paths
        lines.extend([
            "",
            "Paths",
            "-" * 40,
        ])
        lines.append(f"HOP3_ROOT:      {HOP3_ROOT}")
        lines.append(f"Apps dir:       {HOP3_ROOT / 'apps'}")
        lines.append(f"Nginx conf:     {HOP3_ROOT / 'nginx'}")

        return lines

        # registries = result["registries"]
        # print("Configured registries:")
        # for reg in sorted(registries, key=itemgetter("priority")):
        #     msg = (
        #         f'  priority: {reg["priority"]:>2}   '
        #         f'format: {reg["format"]:<16}   '
        #         f'url: {reg["url"]}'
        #     )
        #     print(msg)


@register
class SystemLogsCmd(Command):
    """Show Hop3 server logs.

    Usage: hop3 system:logs [options]

    Options:
        -n, --lines N      Number of lines to show (default: 100)
        --since DURATION   Show logs since duration (e.g., 1h, 30m, 1d)
        --level LEVEL      Filter by log level (DEBUG, INFO, WARNING, ERROR)
        --grep PATTERN     Filter lines matching pattern
        -f, --follow       Follow log output (not yet implemented)

    Examples:
        hop3 system:logs                    # Last 100 lines
        hop3 system:logs -n 50              # Last 50 lines
        hop3 system:logs --since 1h         # Last hour
        hop3 system:logs --level ERROR      # Errors only
        hop3 system:logs --grep deploy      # Lines containing 'deploy'
    """

    name: ClassVar[str] = "system:logs"

    def call(self, *args, **kwargs):
        # Parse options from args (CLI passes them as positional strings)
        parsed = self._parse_args(args)
        lines = parsed.get("lines", 100)
        since = parsed.get("since")
        level = parsed.get("level", "").upper()
        grep = parsed.get("grep", "")

        # Check if log file exists
        if not DEFAULT_LOG_FILE.exists():
            return [{"t": "text", "text": f"No log file found at {DEFAULT_LOG_FILE}"}]

        # Read log file
        with pathlib.Path(DEFAULT_LOG_FILE).open(encoding="utf-8") as f:
            all_lines = f.readlines()

        # Apply --since filter
        if since:
            cutoff = self._parse_since(since)
            if cutoff:
                all_lines = self._filter_by_time(all_lines, cutoff)

        # Apply --level filter
        if level:
            all_lines = [ln for ln in all_lines if f"[{level}]" in ln]

        # Apply --grep filter
        if grep:
            pattern = re.compile(grep, re.IGNORECASE)
            all_lines = [ln for ln in all_lines if pattern.search(ln)]

        # Take last N lines
        result_lines = all_lines[-lines:]

        if not result_lines:
            return [{"t": "text", "text": "No log entries found matching criteria."}]

        return [{"t": "text", "text": "".join(result_lines)}]

    def _parse_since(self, since: str):
        """Parse duration string like '1h', '30m', '1d' into a cutoff datetime."""
        match = re.match(r"^(\d+)([smhd])$", since.lower())
        if not match:
            return None

        value = int(match.group(1))
        unit = match.group(2)

        delta = {
            "s": timedelta(seconds=value),
            "m": timedelta(minutes=value),
            "h": timedelta(hours=value),
            "d": timedelta(days=value),
        }.get(unit)

        if delta:
            return datetime.now(tz=timezone.utc) - delta
        return None

    def _filter_by_time(self, lines: list[str], cutoff) -> list[str]:
        """Filter log lines to only include those after cutoff time."""
        result = []
        for line in lines:
            # Log format: "2025-12-07 10:15:23 [LEVEL] message"
            if len(line) >= 19:
                try:
                    timestamp_str = line[:19]
                    timestamp = datetime.strptime(
                        timestamp_str, "%Y-%m-%d %H:%M:%S"
                    ).replace(tzinfo=timezone.utc)
                    if timestamp >= cutoff:
                        result.append(line)
                except ValueError:
                    # Line doesn't start with valid timestamp, include it anyway
                    # (could be continuation of previous log entry)
                    if result:  # Only if we've started collecting
                        result.append(line)
        return result

    def _parse_args(self, args: tuple) -> dict:
        """Parse CLI arguments into a dictionary.

        Handles:
            -n 50, --lines 50, --lines=50
            --since 1h, --since=1h
            --level ERROR, --level=ERROR
            --grep pattern, --grep=pattern
        """
        result = {}
        args_list = list(args)
        i = 0

        while i < len(args_list):
            arg = args_list[i]

            # Handle -n shorthand
            if arg == "-n" and i + 1 < len(args_list):
                result["lines"] = int(args_list[i + 1])
                i += 2
                continue

            # Handle --key=value format
            if arg.startswith("--") and "=" in arg:
                key, value = arg[2:].split("=", 1)
                if key == "lines":
                    result[key] = int(value)
                else:
                    result[key] = value
                i += 1
                continue

            # Handle --key value format
            if arg.startswith("--") and i + 1 < len(args_list):
                key = arg[2:]
                value = args_list[i + 1]
                if key == "lines":
                    result[key] = int(value)
                else:
                    result[key] = value
                i += 2
                continue

            i += 1

        return result


@register
class CleanupCmd(Command):
    """Clean up unused Docker resources (networks, images, containers, volumes).

    Usage: hop3 system:cleanup [options]

    Options:
        --dry-run       Show what would be cleaned up without actually doing it
        --all           Also remove unused images (not just dangling ones)
        --volumes       Also prune unused volumes (data loss warning!)

    This command removes:
        - Stopped containers
        - Unused networks (not used by any container)
        - Dangling images (untagged)
        - Build cache

    With --all:
        - All unused images (not just dangling)

    With --volumes:
        - Unused volumes (WARNING: may cause data loss!)

    Examples:
        hop3 system:cleanup                # Safe cleanup
        hop3 system:cleanup --dry-run      # Preview what would be cleaned
        hop3 system:cleanup --all          # Include unused images
        hop3 system:cleanup --volumes      # Include volumes (careful!)
    """

    name: ClassVar[str] = "system:cleanup"

    def call(self, *args, **kwargs):
        dry_run = "--dry-run" in args
        include_all = "--all" in args
        include_volumes = "--volumes" in args

        results = []

        if dry_run:
            results.append("=== DRY RUN - No changes will be made ===\n")

        # 1. Network cleanup (most important for the network exhaustion issue)
        results.append(self._cleanup_networks(dry_run))

        # 2. Container cleanup
        results.append(self._cleanup_containers(dry_run))

        # 3. Image cleanup
        results.append(self._cleanup_images(dry_run, include_all))

        # 4. Volume cleanup (only if explicitly requested)
        if include_volumes:
            results.append(self._cleanup_volumes(dry_run))

        # 5. Build cache cleanup
        results.append(self._cleanup_build_cache(dry_run))

        return [{"t": "text", "text": "\n".join(results)}]

    def _cleanup_networks(self, dry_run: bool) -> str:
        """Clean up unused Docker networks."""
        lines = ["Docker Networks:"]

        if dry_run:
            # List networks that would be removed
            result = subprocess.run(
                ["docker", "network", "ls", "--filter", "dangling=true", "-q"],
                capture_output=True,
                text=True,
                check=False,
            )
            network_ids = result.stdout.strip().split("\n")
            network_ids = [n for n in network_ids if n]

            if network_ids:
                lines.append(f"  Would remove {len(network_ids)} unused network(s)")
            else:
                lines.append("  No unused networks to remove")
        else:
            result = subprocess.run(
                ["docker", "network", "prune", "-f"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                # Parse output for deleted networks
                output = result.stdout.strip()
                if "Deleted Networks:" in output:
                    lines.append(f"  {output}")
                else:
                    lines.append("  No unused networks removed")
            else:
                lines.append(f"  Error: {result.stderr.strip()}")

        return "\n".join(lines)

    def _cleanup_containers(self, dry_run: bool) -> str:
        """Clean up stopped containers."""
        lines = ["Docker Containers:"]

        if dry_run:
            result = subprocess.run(
                ["docker", "ps", "-aq", "--filter", "status=exited"],
                capture_output=True,
                text=True,
                check=False,
            )
            container_ids = result.stdout.strip().split("\n")
            container_ids = [c for c in container_ids if c]

            if container_ids:
                lines.append(
                    f"  Would remove {len(container_ids)} stopped container(s)"
                )
            else:
                lines.append("  No stopped containers to remove")
        else:
            result = subprocess.run(
                ["docker", "container", "prune", "-f"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                output = result.stdout.strip()
                if output:
                    # Count deleted containers
                    deleted = output.count("Deleted Containers:")
                    lines.append("  Cleaned up stopped containers")
                else:
                    lines.append("  No stopped containers removed")
            else:
                lines.append(f"  Error: {result.stderr.strip()}")

        return "\n".join(lines)

    def _cleanup_images(self, dry_run: bool, include_all: bool) -> str:
        """Clean up unused Docker images."""
        lines = ["Docker Images:"]

        prune_args = ["docker", "image", "prune", "-f"]
        if include_all:
            prune_args.append("-a")

        if dry_run:
            # List dangling images
            filter_arg = "dangling=true" if not include_all else "dangling=false"
            result = subprocess.run(
                ["docker", "images", "-q", "--filter", "dangling=true"],
                capture_output=True,
                text=True,
                check=False,
            )
            image_ids = result.stdout.strip().split("\n")
            image_ids = [i for i in image_ids if i]

            if include_all:
                lines.append("  Would remove dangling images + all unused images")
            elif image_ids:
                lines.append(f"  Would remove {len(image_ids)} dangling image(s)")
            else:
                lines.append("  No dangling images to remove")
        else:
            result = subprocess.run(
                prune_args,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                output = result.stdout.strip()
                if "Total reclaimed space" in output:
                    # Extract space reclaimed
                    for line in output.split("\n"):
                        if "Total reclaimed space" in line:
                            lines.append(f"  {line}")
                            break
                else:
                    lines.append("  No images removed")
            else:
                lines.append(f"  Error: {result.stderr.strip()}")

        return "\n".join(lines)

    def _cleanup_volumes(self, dry_run: bool) -> str:
        """Clean up unused Docker volumes."""
        lines = ["Docker Volumes (WARNING: may cause data loss!):"]

        if dry_run:
            result = subprocess.run(
                ["docker", "volume", "ls", "-q", "--filter", "dangling=true"],
                capture_output=True,
                text=True,
                check=False,
            )
            volume_ids = result.stdout.strip().split("\n")
            volume_ids = [v for v in volume_ids if v]

            if volume_ids:
                lines.append(f"  Would remove {len(volume_ids)} unused volume(s)")
            else:
                lines.append("  No unused volumes to remove")
        else:
            result = subprocess.run(
                ["docker", "volume", "prune", "-f"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                output = result.stdout.strip()
                if "Total reclaimed space" in output:
                    for line in output.split("\n"):
                        if "Total reclaimed space" in line:
                            lines.append(f"  {line}")
                            break
                else:
                    lines.append("  No volumes removed")
            else:
                lines.append(f"  Error: {result.stderr.strip()}")

        return "\n".join(lines)

    def _cleanup_build_cache(self, dry_run: bool) -> str:
        """Clean up Docker build cache."""
        lines = ["Docker Build Cache:"]

        if dry_run:
            result = subprocess.run(
                ["docker", "builder", "du"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                lines.append("  Would clear build cache")
            else:
                lines.append("  Build cache info unavailable")
        else:
            result = subprocess.run(
                ["docker", "builder", "prune", "-f"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                output = result.stdout.strip()
                if "Total reclaimed space" in output:
                    for line in output.split("\n"):
                        if "Total reclaimed space" in line:
                            lines.append(f"  {line}")
                            break
                else:
                    lines.append("  Build cache cleared")
            else:
                lines.append(f"  Error: {result.stderr.strip()}")

        return "\n".join(lines)
