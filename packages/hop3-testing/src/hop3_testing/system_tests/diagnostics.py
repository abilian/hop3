# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Diagnostic collection for failed tests.

Collects logs and diagnostic information from the server after test failures
to enable offline debugging without manual SSH access.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from hop3_testing.util.ssh import SSHConnection, SSHConnectionInfo

if TYPE_CHECKING:
    from rich.console import Console


@dataclass
class DiagnosticResult:
    """Result of diagnostic collection."""

    timestamp: datetime
    server_ip: str
    output_dir: Path
    collected_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


class DiagnosticCollector:
    """Collects diagnostic information from the server after test failures.

    Gathers:
    - hop3-server logs (journalctl)
    - nginx access/error logs
    - App-specific logs and build logs
    - Docker daemon logs
    - System information
    """

    # Commands to run for collecting diagnostics
    DIAGNOSTIC_COMMANDS: ClassVar[dict[str, str]] = {
        "hop3-server.log": "journalctl -u hop3-server --no-pager -n 500 2>&1 || echo 'No hop3-server logs'",
        "nginx-error.log": "tail -500 /var/log/nginx/error.log 2>&1 || echo 'No nginx error log'",
        "nginx-access.log": "tail -200 /var/log/nginx/access.log 2>&1 || echo 'No nginx access log'",
        "docker-daemon.log": "journalctl -u docker --no-pager -n 200 2>&1 || echo 'No docker logs'",
        "system-info.txt": "echo '=== Disk ===' && df -h && echo '\\n=== Memory ===' && free -h && echo '\\n=== Docker ===' && docker info 2>&1 | head -30",
        "docker-images.txt": "docker images 2>&1 || echo 'Docker not available'",
        "docker-containers.txt": "docker ps -a 2>&1 || echo 'Docker not available'",
        "hop3-apps.txt": "ls -la /home/hop3/apps/ 2>&1 || echo 'No apps directory'",
        "uwsgi-configs.txt": "ls -la /home/hop3/uwsgi-enabled/ 2>&1 && cat /home/hop3/uwsgi-enabled/* 2>&1 || echo 'No uwsgi configs'",
        "nginx-sites.txt": "ls -la /etc/nginx/sites-enabled/ 2>&1 && cat /etc/nginx/sites-enabled/* 2>&1 || echo 'No nginx sites'",
        "recent-builds.log": "find /home/hop3/apps -name 'build.log' -mmin -60 -exec echo '=== {} ===' \\; -exec cat {} \\; 2>&1 || echo 'No recent build logs'",
        "hop3-env.txt": "cat /home/hop3/.env 2>&1 || echo 'No .env file'",
    }

    def __init__(
        self,
        conn: SSHConnection,
        output_base: Path,
        console: Console | None = None,
    ):
        """Initialize the diagnostic collector.

        Args:
            conn: SSH connection to the server.
            output_base: Base directory for storing logs (e.g., ./logs).
            console: Rich console for output.
        """
        self.conn = conn
        self.output_base = output_base
        self.console = console

    def collect(
        self,
        failed_tests: list[str] | None = None,
        existing_output_dir: Path | None = None,
    ) -> DiagnosticResult:
        """Collect all diagnostics from the server.

        Args:
            failed_tests: Optional list of failed test names for targeted collection.
            existing_output_dir: If provided, use this directory instead of creating
                               a new timestamped one. Useful when per-test diagnostics
                               were already collected to this directory.

        Returns:
            DiagnosticResult with collected files and any errors.
        """
        timestamp = datetime.now(tz=UTC)
        if existing_output_dir:
            output_dir = existing_output_dir
            output_dir.mkdir(parents=True, exist_ok=True)
        else:
            output_dir = self._create_output_dir(timestamp)

        result = DiagnosticResult(
            timestamp=timestamp,
            server_ip=self.conn.info.host,
            output_dir=output_dir,
        )

        self._log(f"Collecting diagnostics to {output_dir}")

        # Collect standard diagnostics
        for filename, command in self.DIAGNOSTIC_COMMANDS.items():
            self._collect_command_output(command, output_dir / filename, result)

        # Collect app-specific logs for failed tests
        if failed_tests:
            self._collect_failed_app_logs(failed_tests, output_dir, result)

        # Collect recent Docker build outputs
        self._collect_docker_build_logs(output_dir, result)

        # Write summary
        self._write_summary(result, failed_tests)

        self._log(f"Collected {len(result.collected_files)} diagnostic files")
        if result.errors:
            self._log(f"  Errors: {len(result.errors)}")

        return result

    def _create_output_dir(self, timestamp: datetime) -> Path:
        """Create timestamped output directory."""
        dirname = f"daily-test-{timestamp.strftime('%Y-%m-%d_%H-%M-%S')}"
        output_dir = self.output_base / dirname
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def _collect_command_output(
        self,
        command: str,
        output_path: Path,
        result: DiagnosticResult,
    ) -> None:
        """Run a command and save output to file."""
        try:
            _exit_code, stdout, stderr = self.conn.run(command, timeout=30)

            content = stdout
            if stderr and stderr.strip():
                content += f"\n\n=== STDERR ===\n{stderr}"

            output_path.write_text(content)
            result.collected_files.append(str(output_path.name))

        except Exception as e:
            result.errors.append(f"Failed to collect {output_path.name}: {e}")

    def _collect_failed_app_logs(
        self,
        failed_tests: list[str],
        output_dir: Path,
        result: DiagnosticResult,
    ) -> None:
        """Collect logs specific to failed test apps."""
        apps_dir = output_dir / "failed-apps"
        apps_dir.mkdir(exist_ok=True)

        for test_name in failed_tests:
            # Extract basename from path-style test names (e.g., "apps/real-apps-nix/cryptpad" -> "cryptpad")
            base_name = Path(test_name).name
            # Try to find the app directory (might have timestamp suffix)
            find_cmd = f"find /home/hop3/apps -maxdepth 1 -name '{base_name}*' -type d 2>/dev/null | head -1"
            _exit_code, stdout, _ = self.conn.run(find_cmd, timeout=10)

            app_path = stdout.strip()
            if not app_path:
                continue

            app_name = Path(app_path).name
            app_log_dir = apps_dir / app_name
            app_log_dir.mkdir(exist_ok=True)

            # Collect app logs and diagnostic info
            log_commands = {
                # App-specific files
                "build.log": f"cat {app_path}/log/build.log 2>&1 || echo 'No build log'",
                "app.log": f"cat {app_path}/log/*.log 2>&1 || echo 'No app logs'",
                "env": f"cat {app_path}/ENV 2>&1 || echo 'No ENV file'",
                "hop3.toml": f"cat {app_path}/src/hop3.toml 2>&1 || echo 'No hop3.toml'",
                "Procfile": f"cat {app_path}/src/Procfile 2>&1 || echo 'No Procfile'",
                "Dockerfile": f"cat {app_path}/src/Dockerfile 2>&1 || echo 'No Dockerfile'",
                "docker-compose.yml": f"cat {app_path}/src/docker-compose.yml 2>&1 || cat {app_path}/src/docker-compose.yaml 2>&1 || echo 'No docker-compose'",
                # Server configs
                "nginx.conf": f"cat /home/hop3/nginx/{app_name}.conf 2>&1 || cat /etc/nginx/sites-enabled/{app_name}* 2>&1 || echo 'No nginx config'",
                "uwsgi.ini": f"cat /home/hop3/uwsgi-enabled/{app_name}.ini 2>&1 || echo 'No uwsgi config'",
                # Systemd/journal logs - these are the most useful for debugging
                "journal-hop3-server.log": "journalctl -u hop3-server -n 100 --no-pager 2>&1",
                "journal-uwsgi.log": "journalctl -u uwsgi-hop3 -n 100 --no-pager 2>&1",
                # Process and port info
                "process-info.txt": f"ps aux | grep -E '{app_name}|uwsgi' | grep -v grep 2>&1 || echo 'No processes'",
                "port-info.txt": f"cat {app_path}/PORT 2>&1 && ss -tlnp | grep $(cat {app_path}/PORT 2>/dev/null) 2>&1 || echo 'No port info'",
                # Directory structure for debugging
                "directory-tree.txt": f"find {app_path} -type f 2>&1 | head -50",
            }

            for filename, cmd in log_commands.items():
                try:
                    _exit_code, stdout, _stderr = self.conn.run(cmd, timeout=10)
                    content = stdout.strip()
                    # Skip if empty or contains only error messages
                    if not content:
                        continue
                    # Skip placeholder responses
                    if content in {
                        "No build log",
                        "No app logs",
                        "No ENV file",
                        "No hop3.toml",
                        "No Dockerfile",
                        "No docker-compose",
                        "No nginx config",
                        "No uwsgi config",
                    }:
                        continue
                    # Skip if it's just a cat error followed by placeholder
                    if content.startswith("cat:") and content.endswith((
                        "No build log",
                        "No app logs",
                        "No ENV file",
                        "No hop3.toml",
                        "No Dockerfile",
                        "No docker-compose",
                        "No nginx config",
                        "No uwsgi config",
                    )):
                        continue
                    (app_log_dir / filename).write_text(stdout)
                    result.collected_files.append(f"failed-apps/{app_name}/{filename}")
                except Exception:
                    pass

    def _collect_docker_build_logs(
        self,
        output_dir: Path,
        result: DiagnosticResult,
    ) -> None:
        """Collect recent Docker build attempts and errors."""
        docker_dir = output_dir / "docker"
        docker_dir.mkdir(exist_ok=True)

        # Get recent Docker events
        cmd = "docker events --since '1h' --until 'now' --filter 'type=image' 2>&1 | tail -50 || echo 'No events'"
        self._collect_command_output(cmd, docker_dir / "events.log", result)

        # Get Docker build cache info
        cmd = "docker builder du 2>&1 || echo 'BuildKit not available'"
        self._collect_command_output(cmd, docker_dir / "builder-cache.txt", result)

        # Try to get any failed build contexts that might still exist
        cmd = "ls -la /tmp/docker* 2>&1 || echo 'No temp docker files'"
        self._collect_command_output(cmd, docker_dir / "temp-files.txt", result)

    def _write_summary(
        self,
        result: DiagnosticResult,
        failed_tests: list[str] | None,
    ) -> None:
        """Write a summary file with test results and collected diagnostics."""
        summary = {
            "timestamp": result.timestamp.isoformat(),
            "server_ip": result.server_ip,
            "failed_tests": failed_tests or [],
            "collected_files": result.collected_files,
            "errors": result.errors,
        }

        summary_path = result.output_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, indent=2))
        result.collected_files.append("summary.json")

        # Also write a human-readable summary
        readme = f"""# Diagnostic Collection Summary

**Timestamp:** {result.timestamp.strftime("%Y-%m-%d %H:%M:%S")}
**Server:** {result.server_ip}

## Failed Tests

{chr(10).join(f"- {t}" for t in (failed_tests or [])) or "None specified"}

## Collected Files

{chr(10).join(f"- {f}" for f in result.collected_files)}

## Collection Errors

{chr(10).join(f"- {e}" for e in result.errors) or "None"}

## Quick Debugging

1. Check `hop3-server.log` for server-side errors
2. Check `recent-builds.log` for Docker build failures
3. Check `failed-apps/*/build.log` for specific app build logs
4. Check `nginx-error.log` for proxy issues
"""
        (result.output_dir / "README.md").write_text(readme)

    def _log(self, message: str) -> None:
        """Log a message."""
        if self.console:
            self.console.print(f"  {message}")
        else:
            print(f"  {message}")


def collect_diagnostics(
    server_ip: str,
    output_base: Path | str = Path("./logs"),
    failed_tests: list[str] | None = None,
    console: Console | None = None,
) -> DiagnosticResult:
    """Convenience function to collect diagnostics from a server.

    Args:
        server_ip: Server IP address.
        output_base: Base directory for logs.
        failed_tests: List of failed test names.
        console: Rich console for output.

    Returns:
        DiagnosticResult with collected files.
    """
    output_base = Path(output_base)
    info = SSHConnectionInfo(host=server_ip, user="root")
    conn = SSHConnection(info)

    try:
        if not conn.connect(timeout=30):
            return DiagnosticResult(
                timestamp=datetime.now(tz=UTC),
                server_ip=server_ip,
                output_dir=output_base,
                errors=["Failed to connect to server"],
            )

        collector = DiagnosticCollector(conn, output_base, console)
        return collector.collect(failed_tests)

    finally:
        conn.close()
