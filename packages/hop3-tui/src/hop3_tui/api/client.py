# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""HTTP client for Hop3 JSON-RPC API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from hop3_tui.api.models import App, AppState, Backup, EnvVar, SystemStatus


class Hop3ClientError(Exception):
    """Base exception for Hop3 client errors."""


def _as_count(cell: Any) -> int:
    """A whole number from a table cell. Cells arrive as strings.

    Parsing belongs here, at the boundary, so a screen never formats a raw cell —
    the processes table used to apply `:.1f` to one and raise ValueError on real
    data. An unparseable cell is 0 rather than a crash.
    """
    try:
        return int(str(cell).strip())
    except (TypeError, ValueError):
        return 0


class Hop3Client:
    """Client for communicating with Hop3 server via JSON-RPC."""

    def __init__(
        self,
        base_url: str = "http://localhost:5000",
        token: str | None = None,
        verify_ssl: bool = True,
        ssl_cert: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        # SECURITY: when a pinned cert is configured we always pass its
        # path (chain-verified against the cert). Disabling verification
        # entirely happens only when the operator explicitly sets
        # ``verify_ssl=false`` in config or via ``HOP3_VERIFY_SSL=false``.
        # Mirrors the hop3-cli policy in notes/security.md §3.4.
        if ssl_cert:
            self._verify: bool | str = ssl_cert
        else:
            self._verify = verify_ssl
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

        async with httpx.AsyncClient(verify=self._verify) as client:
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
        result = await self._rpc_call(["app", "list"])
        apps = []
        if result and result.get("t") == "table":
            # `app list` sends [Name, Status, Instances] — no port, runtime or
            # timestamp. The third column used to be read as a port, so the apps
            # table showed the instance count under PORT.
            for row in result.get("rows", []):
                app = App(
                    name=row[0] if len(row) > 0 else "unknown",
                    state=AppState(row[1]) if len(row) > 1 else AppState.STOPPED,
                    workers=_as_count(row[2]) if len(row) > 2 else 1,
                )
                apps.append(app)
        return apps

    async def get_app(self, name: str) -> App | None:
        """Get details for a specific application."""
        result = await self._rpc_call(["app", "status", "--app", name])
        if result:
            # Parse the result based on the format returned
            return App(name=name)
        return None

    async def start_app(self, name: str) -> bool:
        """Start an application."""
        await self._rpc_call(["app", "start", "--app", name])
        return True

    async def stop_app(self, name: str) -> bool:
        """Stop an application."""
        await self._rpc_call(["app", "stop", "--app", name])
        return True

    async def restart_app(self, name: str) -> bool:
        """Restart an application."""
        await self._rpc_call(["app", "restart", "--app", name])
        return True

    async def get_app_logs(self, name: str, lines: int = 100) -> list[str]:
        """Get application logs."""
        result = await self._rpc_call([
            "app",
            "logs",
            "--app",
            name,
            "--lines",
            str(lines),
        ])
        if result and result.get("t") == "text":
            return result.get("text", "").split("\n")
        return []

    # System methods

    async def get_system_status(self) -> SystemStatus:
        """
        Get system status information.

        STUB: the RPC call is made (so the server is exercised), but the
        response is not yet parsed. The server returns the rich-text
        ``system status`` shape; once we surface ``--json`` here and
        reshape ``SystemStatus`` to match (identity + per-section items +
        overall severity), this should hand back real data. Until then the
        TUI dashboard's system pane is intentionally a placeholder.
        """
        # TODO(tui): pass --json to the RPC call and parse into SystemStatus.
        _ = await self._rpc_call(["system", "status"])
        return SystemStatus()

    async def get_system_info(self) -> dict[str, Any]:
        """Get system information."""
        result = await self._rpc_call(["system", "info"])
        return result or {}

    # Backup methods

    async def list_backups(self) -> list[Backup]:
        """
        Get list of all backups.

        STUB: the RPC is invoked but the response is not yet parsed into
        ``Backup`` models. The TUI backup list will be empty until this
        parse is wired up.
        """
        # TODO(tui): parse the ``backup list`` response into Backup models.
        _ = await self._rpc_call(["backup", "list"])
        return []

    async def create_backup(self, app_name: str) -> str:
        """Create a backup for an application."""
        result = await self._rpc_call(["backup", "create", "--app", app_name])
        return result.get("backup_id", "") if result else ""

    # Environment variable methods

    async def get_env_vars(self, app_name: str) -> list[EnvVar]:
        """Get environment variables for an application."""
        result = await self._rpc_call(["env", "show", "--app", app_name])
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
        await self._rpc_call(["env", "set", "--app", app_name, f"{key}={value}"])
        return True

    async def delete_env_var(self, app_name: str, key: str) -> bool:
        """Delete an environment variable."""
        await self._rpc_call(["env", "unset", "--app", app_name, key])
        return True

    async def delete_app(self, name: str) -> bool:
        """Delete an application."""
        await self._rpc_call(["app", "destroy", "--app", name])
        return True

    async def deploy_app(self, name: str) -> dict[str, Any]:
        """Build and start an application from the source it was created with.

        `deploy` takes no repository: the source is fixed when the app is created
        (see `create_app`). The old `--from` flag was never a server option.
        """
        result = await self._rpc_call(["deploy", "--app", name])
        return result or {}

    async def create_app(self, name: str, repo_url: str) -> bool:
        """Create an application from a git repository.

        There is no empty app on the server: `app create` takes the repository to
        create from, and `deploy_app` is what then builds and starts it.
        """
        await self._rpc_call(["app", "create", repo_url, "--app", name])
        return True

    # Addon methods

    async def list_addons(self) -> list[dict[str, Any]]:
        """Get list of all addons."""
        result = await self._rpc_call(["addon", "list"])
        addons = []
        if result and result.get("t") == "table":
            for row in result.get("rows", []):
                # `addon list` sends [Name, Type, Attached apps] — three columns,
                # the third a comma-joined list of apps or "-". There is no status
                # column; reading a fourth gave every add-on "unknown".
                attached = str(row[2]).strip() if len(row) > 2 else ""
                addon = {
                    "name": row[0] if len(row) > 0 else "",
                    "type": row[1] if len(row) > 1 else "",
                    "app_name": None if attached in {"", "-"} else attached,
                }
                addons.append(addon)
        return addons

    async def get_addon(self, name: str) -> dict[str, Any] | None:
        """Get addon details."""
        result = await self._rpc_call(["addon", "show", name])
        return result

    async def create_addon(self, addon_type: str, name: str) -> bool:
        """Create a new addon."""
        await self._rpc_call(["addon", "create", addon_type, name])
        return True

    async def attach_addon(self, addon_name: str, app_name: str) -> bool:
        """Attach an addon to an application."""
        await self._rpc_call(["addon", "attach", addon_name, "--app", app_name])
        return True

    async def detach_addon(self, addon_name: str, app_name: str) -> bool:
        """Detach an addon from an application."""
        await self._rpc_call(["addon", "detach", addon_name, "--app", app_name])
        return True

    async def delete_addon(self, name: str) -> bool:
        """Delete an addon."""
        await self._rpc_call(["addon", "destroy", name])
        return True

    # Extended backup methods

    async def get_backup(self, backup_id: str) -> Backup | None:
        """Get backup details."""
        result = await self._rpc_call(["backup", "show", backup_id])
        if result:
            # Parse created_at from result or use current time as fallback
            created_at_str = result.get("created_at")
            if created_at_str:
                created_at = datetime.fromisoformat(created_at_str)
            else:
                created_at = datetime.now(timezone.utc)

            return Backup(
                id=backup_id,
                app_name=result.get("app_name", ""),
                created_at=created_at,
                size_bytes=result.get("size_bytes", 0),
                addons=result.get("addons", []),
            )
        return None

    async def restore_backup(self, backup_id: str) -> bool:
        """Restore a backup."""
        await self._rpc_call(["backup", "restore", backup_id])
        return True

    async def delete_backup(self, backup_id: str) -> bool:
        """Delete a backup."""
        await self._rpc_call(["backup", "destroy", backup_id])
        return True

    # Process and system log methods

    async def get_processes(self, app_name: str) -> list[dict[str, Any]]:
        """Get the processes of one application.

        `ps` is app-scoped on the server — there is no server-wide process list.
        """
        result = await self._rpc_call(["ps", "--app", app_name])
        processes = []
        if result and result.get("t") == "table":
            for row in result.get("rows", []):
                # `ps` sends [Process Type, Count]: how many workers of each type
                # the app is scaled to. It is not a process list — there is no pid,
                # status, CPU or uptime on the server at all, and the client used to
                # parse six columns out of these two.
                process = {
                    "type": row[0] if len(row) > 0 else "",
                    "count": _as_count(row[1]) if len(row) > 1 else 0,
                }
                processes.append(process)
        return processes

    async def get_system_logs(self, lines: int = 100) -> list[str]:
        """Get system logs."""
        result = await self._rpc_call(["system", "logs", "--lines", str(lines)])
        if result and result.get("t") == "text":
            return result.get("text", "").split("\n")
        return []
