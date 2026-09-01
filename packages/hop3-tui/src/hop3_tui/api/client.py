# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""HTTP client for Hop3 JSON-RPC API."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from hop3_tui.api.models import App, AppState, Backup, EnvVar, SystemStatus

#: Said once, in full, wherever an unconfigured client is used. Naming the two
#: ways out matters more than the diagnosis: the previous behaviour was to guess a
#: server and report its answer as ours.
NOT_CONFIGURED = (
    "No Hop3 server configured. Run `hop3 login` to set one up, "
    "or start the TUI with `hop3-tui --server URL`."
)


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


def _table_rows(result: list[Any]) -> list[list[Any]]:
    """The rows of the table in a response, or none when it carries no table.

    Every list-returning method here reads the same envelope, and each one that
    invented its own reading of it got something wrong: the apps table showed the
    instance count under PORT, the add-ons table read a status column that does not
    exist, and `env show` was parsed as a mapping — which made the environment
    screen list the envelope's own keys (`t`, `text`) as if they were variables.
    """
    for node in result:
        if isinstance(node, dict) and node.get("t") == "table":
            return list(node.get("rows", []))
    return []


def _text(result: list[Any]) -> str:
    """The text nodes of a response, joined. What `logs` and `system logs` send."""
    return "\n".join(
        str(node.get("text", ""))
        for node in result
        if isinstance(node, dict) and node.get("t") == "text"
    )


def _pairs(result: list[Any]) -> dict[str, str]:
    """A two-column `[label, value]` table as a mapping. What `app status` sends."""
    return {
        str(row[0]).strip(): str(row[1]).strip()
        for row in _table_rows(result)
        if len(row) > 1
    }


def _as_state(cell: Any) -> AppState:
    """An `AppState` from a status cell, or a loud failure.

    Not a default: a state we cannot name is a client that has fallen behind its
    server, and showing it as STOPPED would be an invented answer about whether
    someone's application is up.
    """
    try:
        return AppState(str(cell).strip().upper())
    except ValueError as error:
        msg = f"Server reported an unknown application state: {cell!r}"
        raise Hop3ClientError(msg) from error


def _attached(cell: Any) -> str | None:
    """The apps an add-on is attached to, or None. The server writes "-" for none."""
    attached = str(cell).strip()
    return None if attached in {"", "-"} else attached


def _as_port(url: str) -> int | None:
    """The port of `app status`'s `Local URL` row (`http://127.0.0.1:8000`)."""
    return urlparse(url).port if url else None


def _hostname(url: str) -> str | None:
    """The host of `app status`'s `URL` row (`https://blog.example.com`)."""
    return urlparse(url).hostname if url else None


class Hop3Client:
    """Client for communicating with Hop3 server via JSON-RPC."""

    def __init__(
        self,
        base_url: str = "",
        transport_hint: str = "",
        token: str | None = None,
        verify_ssl: bool = True,
        ssl_cert: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        #: Appended to transport failures, to explain a route the URL does not show.
        self.transport_hint = transport_hint
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
    ) -> list[Any]:
        """Send one CLI command, and return the list of output nodes it answered with."""
        if not self.base_url:
            raise Hop3ClientError(NOT_CONFIGURED)

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
                msg = f"Request failed: {e} {self.transport_hint}".rstrip()
                raise Hop3ClientError(msg) from e

            data = response.json()
            if "error" in data:
                raise Hop3ClientError(data["error"].get("message", "Unknown error"))
            result = data.get("result")
            # A command answers with a *list* of output nodes — `env show` sends a
            # caption, a table and a footnote. Keeping only the first threw the
            # table away and left the caption to be parsed as the data.
            return result if isinstance(result, list) else []

    # Application methods

    async def list_apps(self) -> list[App]:
        """Get list of all applications."""
        result = await self._rpc_call(["app", "list"])
        # `app list` sends [Name, Status, Instances] — no port, runtime or
        # timestamp. The third column used to be read as a port, so the apps
        # table showed the instance count under PORT.
        return [
            App(
                name=row[0] if len(row) > 0 else "unknown",
                state=_as_state(row[1]) if len(row) > 1 else AppState.STOPPED,
                workers=_as_count(row[2]) if len(row) > 2 else 1,
            )
            for row in _table_rows(result)
        ]

    async def get_app(self, name: str) -> App | None:
        """Get details for one application, from `app status`'s property table.

        The response used to be fetched and then dropped on the floor, and an
        `App(name=name)` — every other field its model default — handed back as if
        it had been read from the server. The detail screen showed those defaults:
        a STOPPED badge on a running app, and a port of `-`.
        """
        result = await self._rpc_call(["app", "status", "--app", name])
        properties = _pairs(result)
        if not properties:
            return None
        return App(
            name=properties.get("Name", name),
            state=_as_state(properties.get("Status", "")),
            workers=_as_count(properties["Instances"])
            if "Instances" in properties
            else 1,
            port=_as_port(properties.get("Local URL", "")),
            hostname=_hostname(properties.get("URL", "")),
            error_message=properties.get("Error"),
        )

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
        return _text(result).split("\n")

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

    # Backup methods

    async def list_backups(self) -> list[Backup]:
        """Every backup the server knows about.

        `backup list` sends [BACKUP ID, APP, SIZE, CREATED, STATUS, SERVICES], with
        the size and the timestamp already formatted for reading. `Backup` mirrors
        that, rather than parsing a rendered size back into bytes so the screen can
        render it again — which is the round trip that left every row's size blank.
        """
        result = await self._rpc_call(["backup", "list"])
        return [
            Backup(
                id=str(row[0]),
                app_name=str(row[1]),
                size=str(row[2]),
                created=str(row[3]),
                state=str(row[4]),
                addons=str(row[5]),
            )
            for row in _table_rows(result)
            if len(row) > 5
        ]

    async def create_backup(self, app_name: str) -> None:
        """Create a backup for an application."""
        await self._rpc_call(["backup", "create", "--app", app_name])

    # Environment variable methods

    async def get_env_vars(
        self, app_name: str, *, show_secrets: bool = False
    ) -> list[EnvVar]:
        """The app's configured environment, as `env show` sends it.

        `env show` answers with a `[Key, Value]` table, and redacts every value
        whose name looks like a credential unless `--show-secrets` is passed. This
        used to read the response as a mapping of names to values: what it got was
        the JSON envelope, so the screen listed `t` and `text` as an app's two
        environment variables and never showed a real one.
        """
        args = ["env", "show", "--app", app_name]
        if show_secrets:
            args.append("--show-secrets")
        result = await self._rpc_call(args)
        return [
            EnvVar(name=str(row[0]), value=str(row[1]))
            for row in _table_rows(result)
            if len(row) > 1
        ]

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

    async def deploy_app(self, name: str) -> None:
        """Build and start an application from the source it was created with.

        `deploy` takes no repository: the source is fixed when the app is created
        (see `create_app`). The old `--from` flag was never a server option.
        """
        await self._rpc_call(["deploy", "--app", name])

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
        # `addon list` sends [Name, Type, Attached apps] — three columns, the third
        # a comma-joined list of apps or "-". There is no status column; reading a
        # fourth gave every add-on "unknown".
        return [
            {
                "name": row[0] if len(row) > 0 else "",
                "type": row[1] if len(row) > 1 else "",
                "app_name": _attached(row[2]) if len(row) > 2 else None,
            }
            for row in _table_rows(result)
        ]

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
        # `ps` sends [Process Type, Count]: how many workers of each type the app is
        # scaled to. It is not a process list — there is no pid, status, CPU or
        # uptime on the server at all, and the client used to parse six columns out
        # of these two.
        return [
            {
                "type": row[0] if len(row) > 0 else "",
                "count": _as_count(row[1]) if len(row) > 1 else 0,
            }
            for row in _table_rows(result)
        ]

    async def get_system_logs(self, lines: int = 100) -> list[str]:
        """Get system logs."""
        result = await self._rpc_call(["system", "logs", "--lines", str(lines)])
        return _text(result).split("\n")
