# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Debug utilities for deployment testing.

This module provides debug helpers for inspecting deployed applications:
- Nginx configuration inspection
- App logs inspection
- Directory structure inspection

Debug output is:
1. Printed to console for immediate feedback
2. Added to DiagnosticCollector (if provided) for HTML/JSON reports
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from hop3_testing.util.console import Console, PrintingConsole

if TYPE_CHECKING:
    from hop3_testing.diagnostics import DiagnosticCollector
    from hop3_testing.targets.base import DeploymentTarget


@dataclass(frozen=True)
class DeploymentDebugger:
    """Debug helper for deployed applications.

    Provides utilities for inspecting the state of deployed apps
    on the target server. Outputs to both console and diagnostics.
    """

    target: DeploymentTarget
    """Deployment target."""

    app_name: str
    """Name of the deployed app."""

    console: Console = field(default_factory=PrintingConsole)
    """Console for output."""

    diagnostics: DiagnosticCollector | None = field(default=None)
    """Optional diagnostics collector for persistent reports."""

    def show_nginx_config(self) -> None:
        """Print nginx configuration for the app."""
        self.console.header(f"DEBUG: Nginx config for {self.app_name}")

        try:
            # Check if nginx config exists
            _exit_code, stdout, _stderr = self.target.exec_run(
                f"test -f /home/hop3/nginx/{self.app_name}.conf && "
                "echo 'exists' || echo 'missing'"
            )

            config_content = None
            if "exists" in stdout:
                self.console.success(
                    f"Nginx config found at /home/hop3/nginx/{self.app_name}.conf"
                )

                # Show config content
                _exit_code, config_content, _stderr = self.target.exec_run(
                    f"cat /home/hop3/nginx/{self.app_name}.conf"
                )
                self.console.status("Config content:")
                self.console.echo(config_content)
            else:
                self.console.error(
                    f"Nginx config NOT found at /home/hop3/nginx/{self.app_name}.conf"
                )

            # Check nginx status
            nginx_status = self._get_nginx_status()
            self._show_nginx_status()

            # Check nginx error logs
            nginx_errors = self._get_nginx_errors()
            self._show_nginx_errors()

            # Add to diagnostics for reports
            if self.diagnostics:
                self.diagnostics.add_debug(
                    layer="app",
                    operation="nginx_config",
                    message=f"Nginx config for {self.app_name}",
                    details={
                        "config_exists": "exists" in stdout,
                        "config_path": f"/home/hop3/nginx/{self.app_name}.conf",
                        "nginx_status": nginx_status,
                    },
                    stdout=config_content or "",
                    stderr=nginx_errors,
                )

        except Exception as e:
            self.console.error(f"Error getting nginx debug info: {e}")
            if self.diagnostics:
                self.diagnostics.add_failure(
                    layer="app",
                    operation="nginx_config",
                    message=f"Failed to get nginx config: {e}",
                )

        self.console.separator()

    def show_app_logs(self) -> None:
        """Print app logs."""
        self.console.header(f"DEBUG: App logs for {self.app_name}")

        try:
            # Check app directory structure
            app_structure = self._get_app_structure()
            self._show_app_structure()

            # Check src directory
            src_structure = self._get_src_structure()
            self._show_src_structure()

            # Check logs directory
            log_structure = self._get_log_structure()
            self._show_log_structure()

            # Show log contents
            log_contents = self._get_log_contents()
            self._show_log_contents()

            # Add to diagnostics for reports
            if self.diagnostics:
                self.diagnostics.add_debug(
                    layer="app",
                    operation="app_logs",
                    message=f"App logs for {self.app_name}",
                    details={
                        "app_dir": f"/home/hop3/apps/{self.app_name}",
                        "app_structure": app_structure,
                        "src_structure": src_structure,
                        "log_structure": log_structure,
                    },
                    stdout=log_contents,
                )

        except Exception as e:
            self.console.error(f"Error getting app debug info: {e}")
            if self.diagnostics:
                self.diagnostics.add_failure(
                    layer="app",
                    operation="app_logs",
                    message=f"Failed to get app logs: {e}",
                )

        self.console.separator()

    def _get_nginx_status(self) -> str:
        """Get nginx service status."""
        _exit_code, stdout, _stderr = self.target.exec_run(
            "systemctl is-active nginx 2>/dev/null || "
            "service nginx status 2>/dev/null || echo 'unknown'"
        )
        return stdout.strip()

    def _show_nginx_status(self) -> None:
        """Show nginx service status."""
        self.console.status("Nginx status:")
        self.console.echo(self._get_nginx_status())

    def _get_nginx_errors(self) -> str:
        """Get nginx error log."""
        _exit_code, stdout, _stderr = self.target.exec_run(
            "tail -n 20 /var/log/nginx/error.log 2>/dev/null || echo 'No error log'"
        )
        return stdout

    def _show_nginx_errors(self) -> None:
        """Show nginx error log."""
        self.console.status("Nginx error log (last 20 lines):")
        self.console.echo(self._get_nginx_errors())

    def _get_app_structure(self) -> str:
        """Get app directory structure."""
        _exit_code, stdout, _stderr = self.target.exec_run(
            f"ls -la /home/hop3/apps/{self.app_name}/ 2>/dev/null || "
            "echo 'App directory not found'"
        )
        return stdout

    def _show_app_structure(self) -> None:
        """Show app directory structure."""
        self.console.status("App directory structure:")
        self.console.echo(self._get_app_structure())

    def _get_src_structure(self) -> str:
        """Get src directory structure."""
        _exit_code, stdout, _stderr = self.target.exec_run(
            f"ls -la /home/hop3/apps/{self.app_name}/src/ 2>/dev/null || "
            "echo 'Src directory not found'"
        )
        return stdout

    def _show_src_structure(self) -> None:
        """Show src directory structure."""
        self.console.status("Src directory:")
        self.console.echo(self._get_src_structure())

    def _get_log_structure(self) -> str:
        """Get log directory structure."""
        _exit_code, stdout, _stderr = self.target.exec_run(
            f"ls -la /home/hop3/apps/{self.app_name}/log/ 2>/dev/null || "
            "echo 'Log directory not found'"
        )
        return stdout

    def _show_log_structure(self) -> None:
        """Show log directory structure."""
        self.console.status("Log directory:")
        self.console.echo(self._get_log_structure())

    def _get_log_contents(self) -> str:
        """Get log file contents."""
        _exit_code, stdout, _stderr = self.target.exec_run(
            f"find /home/hop3/apps/{self.app_name}/log -type f "
            "-exec tail -n 10 {} \\; 2>/dev/null || echo 'No log files'"
        )
        return stdout

    def _show_log_contents(self) -> None:
        """Show log file contents."""
        stdout = self._get_log_contents()
        if stdout.strip():
            self.console.status("Log contents:")
            self.console.echo(stdout)

    def show_docker_debug(self) -> None:
        """Print Docker-specific debug information."""
        self.console.header(f"DEBUG: Docker info for {self.app_name}")

        try:
            # Check Docker containers
            self.console.status("Docker containers:")
            _exit, stdout, _ = self.target.exec_run("docker ps -a | head -20")
            self.console.echo(stdout)

            # Check if our container exists
            container_name = f"{self.app_name}-web-1"
            self.console.status(f"Container {container_name} status:")
            _exit, stdout, _ = self.target.exec_run(
                f"docker inspect {container_name} --format "
                "'{{.State.Status}} exit={{.State.ExitCode}} error={{.State.Error}}' "
                "2>/dev/null || echo 'Container not found'"
            )
            self.console.echo(stdout)

            # Get container logs
            self.console.status("Container logs (last 30 lines):")
            _exit, stdout, _ = self.target.exec_run(
                f"docker logs {container_name} 2>&1 | tail -30"
            )
            self.console.echo(stdout)

            # Check the generated compose file
            self.console.status("Generated compose file:")
            _exit, stdout, _ = self.target.exec_run(
                f"cat /home/hop3/apps/{self.app_name}/src/.hop3-compose.yml "
                "2>/dev/null || echo 'Compose file not found'"
            )
            self.console.echo(stdout)

            # Check if app port is accessible
            self.console.status("Checking app connectivity:")
            _exit, port_output, _ = self.target.exec_run(
                f"docker port {container_name} 2>/dev/null | head -1"
            )
            if "->" in port_output:
                host_port = port_output.strip().split("->")[1].strip()
                self.console.echo(f"Port mapping: {port_output.strip()}")

                _exit, stdout, _ = self.target.exec_run(
                    f"curl -s -o /dev/null -w 'HTTP Status: %{{http_code}}\\n' "
                    f"http://{host_port}/ || echo 'Connection failed'"
                )
                self.console.echo(stdout)

            # Check database environment in container
            self.console.status("Database environment in container:")
            _exit, stdout, _ = self.target.exec_run(
                f"docker exec {container_name} env 2>/dev/null | "
                "grep -E '(DATABASE|MYSQL|POSTGRES|REDIS|PG)' || echo 'No DB env vars'"
            )
            self.console.echo(stdout)

            # Add to diagnostics
            if self.diagnostics:
                self.diagnostics.add_debug(
                    layer="app",
                    operation="docker_debug",
                    message=f"Docker debug for {self.app_name}",
                    details={"container_name": container_name},
                )

        except Exception as e:
            self.console.error(f"Error getting Docker debug info: {e}")

        self.console.separator()

    def show_uwsgi_debug(self) -> None:
        """Print uWSGI-specific debug information."""
        self.console.header(f"DEBUG: uWSGI info for {self.app_name}")

        try:
            # Check uWSGI config
            self.console.status("uWSGI config:")
            _exit, stdout, _ = self.target.exec_run(
                f"cat /home/hop3/uwsgi-enabled/{self.app_name}_web.1.ini "
                "2>/dev/null | head -30 || echo 'Config not found'"
            )
            self.console.echo(stdout)

            # Check uWSGI logs
            self.console.status("uWSGI logs (last 30 lines):")
            _exit, stdout, _ = self.target.exec_run(
                f"tail -30 /home/hop3/apps/{self.app_name}/log/web.1.log "
                "2>/dev/null || echo 'Log not found'"
            )
            self.console.echo(stdout)

            # Check app port from config
            self.console.status("App port configuration:")
            _exit, stdout, _ = self.target.exec_run(
                f"grep 'env = PORT=' /home/hop3/uwsgi-enabled/{self.app_name}_web.1.ini "
                "2>/dev/null || echo 'Port not configured'"
            )
            port = None
            if "PORT=" in stdout:
                port = stdout.split("PORT=")[1].strip()
                self.console.echo(f"Configured PORT: {port}")

                # Check HTTP connectivity
                self.console.status("HTTP connectivity test:")
                _exit, stdout, _ = self.target.exec_run(
                    f"curl -s -o /dev/null -w 'HTTP Status: %{{http_code}}\\n' "
                    f"http://127.0.0.1:{port}/ 2>/dev/null || echo 'Connection failed'"
                )
                self.console.echo(stdout)

            # Check if process is running
            self.console.status("Process status:")
            _exit, stdout, _ = self.target.exec_run(
                f"pgrep -f 'apps/{self.app_name}' && echo 'Process found' "
                "|| echo 'No process running'"
            )
            self.console.echo(stdout)

            # Check LIVE_ENV
            self.console.status("Environment variables (LIVE_ENV):")
            _exit, stdout, _ = self.target.exec_run(
                f"cat /home/hop3/apps/{self.app_name}/venv/LIVE_ENV "
                "2>/dev/null | head -20 || echo 'LIVE_ENV not found'"
            )
            self.console.echo(stdout)

            # Add to diagnostics
            if self.diagnostics:
                self.diagnostics.add_debug(
                    layer="app",
                    operation="uwsgi_debug",
                    message=f"uWSGI debug for {self.app_name}",
                    details={"port": port},
                )

        except Exception as e:
            self.console.error(f"Error getting uWSGI debug info: {e}")

        self.console.separator()

    def show_all_rich(self, deployment_type: str = "auto") -> None:
        """Show all debug information including type-specific debugging.

        Args:
            deployment_type: "docker", "native", "nix", or "auto" (auto-detect)
        """
        # Basic debugging
        self.show_nginx_config()
        self.show_app_logs()

        # Type-specific debugging
        if deployment_type == "auto":
            deployment_type = self._detect_deployment_type()

        if deployment_type == "docker":
            self.show_docker_debug()
        else:
            # native, nix, and anything else uses uWSGI
            self.show_uwsgi_debug()

    def _detect_deployment_type(self) -> str:
        """Detect if app is deployed as Docker or native."""
        # Check for Docker container
        container_name = f"{self.app_name}-web-1"
        exit_code, stdout, _ = self.target.exec_run(
            f"docker inspect {container_name} --format '{{{{.State.Status}}}}' "
            "2>/dev/null"
        )
        if exit_code == 0 and stdout.strip():
            return "docker"

        # Check for uWSGI config
        _exit_code, stdout, _ = self.target.exec_run(
            f"test -f /home/hop3/uwsgi-enabled/{self.app_name}_web.1.ini && echo 'exists'"
        )
        if "exists" in stdout:
            return "native"

        return "native"  # Default to native
