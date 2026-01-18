# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Debug utilities for deployment testing.

This module provides debug helpers for inspecting deployed applications:
- Nginx configuration inspection
- App logs inspection
- Directory structure inspection
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from hop3_testing.util.console import Console, PrintingConsole

if TYPE_CHECKING:
    from hop3_testing.targets.base import DeploymentTarget


@dataclass(frozen=True)
class DeploymentDebugger:
    """Debug helper for deployed applications.

    Provides utilities for inspecting the state of deployed apps
    on the target server.
    """

    target: DeploymentTarget
    """Deployment target."""

    app_name: str
    """Name of the deployed app."""

    console: Console = field(default_factory=PrintingConsole)
    """Console for output."""

    def show_nginx_config(self) -> None:
        """Print nginx configuration for the app."""
        self.console.header(f"DEBUG: Nginx config for {self.app_name}")

        try:
            # Check if nginx config exists
            _exit_code, stdout, _stderr = self.target.exec_run(
                f"test -f /home/hop3/nginx/{self.app_name}.conf && "
                "echo 'exists' || echo 'missing'"
            )

            if "exists" in stdout:
                self.console.success(
                    f"Nginx config found at /home/hop3/nginx/{self.app_name}.conf"
                )

                # Show config content
                _exit_code, stdout, _stderr = self.target.exec_run(
                    f"cat /home/hop3/nginx/{self.app_name}.conf"
                )
                self.console.status("Config content:")
                self.console.echo(stdout)
            else:
                self.console.error(
                    f"Nginx config NOT found at /home/hop3/nginx/{self.app_name}.conf"
                )

            # Check nginx status
            self._show_nginx_status()

            # Check nginx error logs
            self._show_nginx_errors()

        except Exception as e:
            self.console.error(f"Error getting nginx debug info: {e}")

        self.console.separator()

    def show_app_logs(self) -> None:
        """Print app logs."""
        self.console.header(f"DEBUG: App logs for {self.app_name}")

        try:
            # Check app directory structure
            self._show_app_structure()

            # Check src directory
            self._show_src_structure()

            # Check logs directory
            self._show_log_structure()

            # Show log contents
            self._show_log_contents()

        except Exception as e:
            self.console.error(f"Error getting app debug info: {e}")

        self.console.separator()

    def show_all(self) -> None:
        """Show all debug information."""
        self.show_nginx_config()
        self.show_app_logs()

    def get_nginx_config(self) -> str | None:
        """Get nginx config content.

        Returns:
            Config content or None if not found
        """
        try:
            exit_code, stdout, stderr = self.target.exec_run(
                f"cat /home/hop3/nginx/{self.app_name}.conf 2>/dev/null"
            )
            if exit_code == 0:
                return stdout
        except Exception:
            pass
        return None

    def get_app_logs(self) -> dict[str, str]:
        """Get all app log file contents.

        Returns:
            Dict mapping log filename to content
        """
        logs = {}
        try:
            # List log files
            exit_code, stdout, stderr = self.target.exec_run(
                f"find /home/hop3/apps/{self.app_name}/log -type f 2>/dev/null"
            )
            if exit_code == 0 and stdout.strip():
                for log_path in stdout.strip().split("\n"):
                    if log_path:
                        _, content, _ = self.target.exec_run(f"cat {log_path}")
                        logs[log_path] = content
        except Exception:
            pass
        return logs

    def _show_nginx_status(self) -> None:
        """Show nginx service status."""
        self.console.status("Nginx status:")
        _exit_code, stdout, _stderr = self.target.exec_run(
            "systemctl is-active nginx 2>/dev/null || "
            "service nginx status 2>/dev/null || echo 'unknown'"
        )
        self.console.echo(stdout)

    def _show_nginx_errors(self) -> None:
        """Show nginx error log."""
        self.console.status("Nginx error log (last 20 lines):")
        _exit_code, stdout, _stderr = self.target.exec_run(
            "tail -n 20 /var/log/nginx/error.log 2>/dev/null || echo 'No error log'"
        )
        self.console.echo(stdout)

    def _show_app_structure(self) -> None:
        """Show app directory structure."""
        _exit_code, stdout, _stderr = self.target.exec_run(
            f"ls -la /home/hop3/apps/{self.app_name}/ 2>/dev/null || "
            "echo 'App directory not found'"
        )
        self.console.status("App directory structure:")
        self.console.echo(stdout)

    def _show_src_structure(self) -> None:
        """Show src directory structure."""
        _exit_code, stdout, _stderr = self.target.exec_run(
            f"ls -la /home/hop3/apps/{self.app_name}/src/ 2>/dev/null || "
            "echo 'Src directory not found'"
        )
        self.console.status("Src directory:")
        self.console.echo(stdout)

    def _show_log_structure(self) -> None:
        """Show log directory structure."""
        _exit_code, stdout, _stderr = self.target.exec_run(
            f"ls -la /home/hop3/apps/{self.app_name}/log/ 2>/dev/null || "
            "echo 'Log directory not found'"
        )
        self.console.status("Log directory:")
        self.console.echo(stdout)

    def _show_log_contents(self) -> None:
        """Show log file contents."""
        _exit_code, stdout, _stderr = self.target.exec_run(
            f"find /home/hop3/apps/{self.app_name}/log -type f "
            "-exec tail -n 10 {} \\; 2>/dev/null || echo 'No log files'"
        )
        if stdout.strip():
            self.console.status("Log contents:")
            self.console.echo(stdout)
