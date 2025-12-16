# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""HTTP client for Hop3 JSON-RPC API."""

from __future__ import annotations

from typing import Any

import httpx

from hop3_tui.api.models import App, AppState, Backup, EnvVar, SystemStatus


class Hop3ClientError(Exception):
    """Base exception for Hop3 client errors."""


class Hop3Client:
    """Client for communicating with Hop3 server via JSON-RPC."""

    def __init__(
        self,
        base_url: str = "http://localhost:5000",
        token: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._request_id = 0

    def _get_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _next_request_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _rpc_call(
        self,
        cli_args: list[str],
        extra_args: dict[str, Any] | None = None,
    ) -> Any:
        """Make a JSON-RPC call to the server."""
        payload = {
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {
                "cli_args": cli_args,
                "extra_args": extra_args or {},
            },
            "id": self._next_request_id(),
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/rpc",
                    json=payload,
                    headers=self._get_headers(),
                    timeout=30.0,
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                msg = f"HTTP error: {e.response.status_code}"
                raise Hop3ClientError(msg) from e
            except httpx.RequestError as e:
                msg = f"Request failed: {e}"
                raise Hop3ClientError(msg) from e

            data = response.json()
            if "error" in data:
                raise Hop3ClientError(data["error"].get("message", "Unknown error"))
            result = data.get("result")
            # Server returns result as a list - extract first element if present
            if isinstance(result, list) and len(result) > 0:
                return result[0]
            return result

    # Application methods

    async def list_apps(self) -> list[App]:
        """Get list of all applications."""
        result = await self._rpc_call(["apps"])
        apps = []
        if result and result.get("t") == "table":
            for row in result.get("rows", []):
                # Assuming row format: [name, status, port, ...]
                app = App(
                    name=row[0] if len(row) > 0 else "unknown",
                    state=AppState(row[1]) if len(row) > 1 else AppState.STOPPED,
                    port=int(row[2]) if len(row) > 2 and row[2] else None,
                )
                apps.append(app)
        return apps

    async def get_app(self, name: str) -> App | None:
        """Get details for a specific application."""
        result = await self._rpc_call(["app:status", name])
        if result:
            # Parse the result based on the format returned
            return App(name=name)
        return None

    async def start_app(self, name: str) -> bool:
        """Start an application."""
        await self._rpc_call(["app:start", name])
        return True

    async def stop_app(self, name: str) -> bool:
        """Stop an application."""
        await self._rpc_call(["app:stop", name])
        return True

    async def restart_app(self, name: str) -> bool:
        """Restart an application."""
        await self._rpc_call(["app:restart", name])
        return True

    async def get_app_logs(self, name: str, lines: int = 100) -> list[str]:
        """Get application logs."""
        result = await self._rpc_call(["app:logs", name, "--lines", str(lines)])
        if result and result.get("t") == "text":
            return result.get("text", "").split("\n")
        return []

    # System methods

    async def get_system_status(self) -> SystemStatus:
        """Get system status information."""
        result = await self._rpc_call(["system:status"])
        # Parse result into SystemStatus model
        return SystemStatus()

    async def get_system_info(self) -> dict[str, Any]:
        """Get system information."""
        result = await self._rpc_call(["system:info"])
        return result or {}

    # Backup methods

    async def list_backups(self) -> list[Backup]:
        """Get list of all backups."""
        result = await self._rpc_call(["backup:list"])
        backups = []
        # Parse result into Backup models
        return backups

    async def create_backup(self, app_name: str) -> str:
        """Create a backup for an application."""
        result = await self._rpc_call(["backup:create", app_name])
        return result.get("backup_id", "") if result else ""

    # Environment variable methods

    async def get_env_vars(self, app_name: str) -> list[EnvVar]:
        """Get environment variables for an application."""
        result = await self._rpc_call(["config:show", app_name])
        env_vars = []
        if result:
            # Result is expected to be a dict or list of env vars
            if isinstance(result, dict):
                for key, value in result.items():
                    # Service vars typically have specific prefixes
                    is_service = key.startswith(("DATABASE_", "REDIS_", "PORT", "HOST"))
                    env_vars.append(
                        EnvVar(name=key, value=str(value), is_service_var=is_service)
                    )
            elif isinstance(result, list):
                for item in result:
                    if isinstance(item, dict):
                        env_vars.append(
                            EnvVar(
                                name=item.get("name", ""),
                                value=item.get("value", ""),
                                is_service_var=item.get("is_service_var", False),
                            )
                        )
        return env_vars

    async def set_env_var(self, app_name: str, key: str, value: str) -> bool:
        """Set an environment variable."""
        await self._rpc_call(["config:set", app_name, f"{key}={value}"])
        return True

    async def delete_env_var(self, app_name: str, key: str) -> bool:
        """Delete an environment variable."""
        await self._rpc_call(["config:unset", app_name, key])
        return True

    async def delete_app(self, name: str) -> bool:
        """Delete an application."""
        await self._rpc_call(["app:destroy", name])
        return True

    async def deploy_app(self, name: str, git_url: str) -> dict[str, Any]:
        """Deploy an application from a git URL."""
        result = await self._rpc_call(["app:deploy", name, "--from", git_url])
        return result or {}

    async def create_app(self, name: str) -> bool:
        """Create an empty application."""
        await self._rpc_call(["app:create", name])
        return True

    # Addon methods

    async def list_addons(self) -> list[dict[str, Any]]:
        """Get list of all addons."""
        result = await self._rpc_call(["addons:list"])
        addons = []
        if result and result.get("t") == "table":
            for row in result.get("rows", []):
                addon = {
                    "name": row[0] if len(row) > 0 else "",
                    "type": row[1] if len(row) > 1 else "",
                    "app_name": row[2] if len(row) > 2 else None,
                    "status": row[3] if len(row) > 3 else "unknown",
                }
                addons.append(addon)
        return addons

    async def get_addon(self, name: str) -> dict[str, Any] | None:
        """Get addon details."""
        result = await self._rpc_call(["addons:info", name])
        return result

    async def create_addon(self, addon_type: str, name: str) -> bool:
        """Create a new addon."""
        await self._rpc_call(["addons:create", addon_type, name])
        return True

    async def attach_addon(self, addon_name: str, app_name: str) -> bool:
        """Attach an addon to an application."""
        await self._rpc_call(["addons:attach", addon_name, app_name])
        return True

    async def detach_addon(self, addon_name: str, app_name: str) -> bool:
        """Detach an addon from an application."""
        await self._rpc_call(["addons:detach", addon_name, app_name])
        return True

    async def delete_addon(self, name: str) -> bool:
        """Delete an addon."""
        await self._rpc_call(["addons:destroy", name])
        return True

    # Extended backup methods

    async def get_backup(self, backup_id: str) -> Backup | None:
        """Get backup details."""
        result = await self._rpc_call(["backup:info", backup_id])
        if result:
            return Backup(
                id=backup_id,
                app_name=result.get("app_name", ""),
                size_bytes=result.get("size_bytes", 0),
                addons=result.get("addons", []),
            )
        return None

    async def restore_backup(self, backup_id: str) -> bool:
        """Restore a backup."""
        await self._rpc_call(["backup:restore", backup_id])
        return True

    async def delete_backup(self, backup_id: str) -> bool:
        """Delete a backup."""
        await self._rpc_call(["backup:delete", backup_id])
        return True

    # Process and system log methods

    async def get_processes(self) -> list[dict[str, Any]]:
        """Get list of running processes."""
        result = await self._rpc_call(["system:processes"])
        processes = []
        if result and result.get("t") == "table":
            for row in result.get("rows", []):
                process = {
                    "name": row[0] if len(row) > 0 else "",
                    "pid": row[1] if len(row) > 1 else 0,
                    "status": row[2] if len(row) > 2 else "unknown",
                    "cpu": row[3] if len(row) > 3 else 0.0,
                    "memory": row[4] if len(row) > 4 else 0.0,
                }
                processes.append(process)
        return processes

    async def get_system_logs(self, lines: int = 100) -> list[str]:
        """Get system logs."""
        result = await self._rpc_call(["system:logs", "--lines", str(lines)])
        if result and result.get("t") == "text":
            return result.get("text", "").split("\n")
        return []
