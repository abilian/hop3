# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""`hop3 tunnel <name>` — open a local SSH tunnel to a remote addon.

Forwards a local port to the addon's port on the server (over the same SSH
connection used for RPC) and prints a ready-to-paste local connection URL.
Holds the tunnel open until interrupted with Ctrl-C.

This is a client-side command: port forwarding necessarily happens on the
developer's machine. It asks the server for the addon's endpoint via the
type-agnostic `addon endpoint <name>` RPC, then drives `sshtunnel` (already a
hop3-cli dependency, same auth path as the RPC tunnel).
"""

from __future__ import annotations

import sys
import time
from typing import TYPE_CHECKING
from urllib.parse import urlparse, urlunparse

from hop3_cli.exit_codes import ExitCode

if TYPE_CHECKING:
    from hop3_cli.config import Config
    from hop3_cli.ui.rich_printer import RichPrinter

# How often the foreground loop re-checks that the tunnel is still up. Short
# enough that a dropped SSH connection surfaces promptly; Ctrl-C interrupts the
# sleep regardless.
_POLL_SECONDS = 5


def handle_tunnel(args: list[str], config: Config, printer: RichPrinter) -> None:
    """Open an SSH tunnel to the named addon and hold it open."""
    name, local_port = _parse_args(args)
    if not name:
        print(
            "Usage: hop3 tunnel <addon-name> [--port <localport>]",
            file=sys.stderr,
        )
        sys.exit(ExitCode.USAGE_ERROR)

    info = _fetch_endpoint(config, name)
    remote_port = int(info["port"])
    bind_port = local_port if local_port is not None else remote_port

    ssh = _ssh_params(config)
    forwarder = _start_forwarder(ssh, remote_port, bind_port)

    bound = forwarder.local_bind_port
    local_url = _rewrite_url(info["url"], bound)
    print(f"Tunnel open to {info['type']} addon '{name}'.")
    print(f"  Local URL:  {local_url}")
    print(f"  Forwarding: 127.0.0.1:{bound} -> {ssh['host']}:{remote_port}")
    print("  Press Ctrl-C to close.")
    try:
        while forwarder.is_active:
            time.sleep(_POLL_SECONDS)
        # Loop exited without Ctrl-C: the SSH connection dropped. Don't pretend
        # the tunnel is still serving — say so loudly and fail.
        print("Tunnel closed: the SSH connection dropped.", file=sys.stderr)
        forwarder.stop()
        sys.exit(ExitCode.NETWORK_ERROR)
    except KeyboardInterrupt:
        print("\nClosing tunnel.")
    finally:
        forwarder.stop()


def _parse_args(args: list[str]) -> tuple[str | None, int | None]:
    """Extract the addon name and optional --port from the argument list."""
    name: str | None = None
    local_port: int | None = None
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--port":
            i += 1
            if i < len(args):
                local_port = _int_or_exit(args[i])
        elif arg.startswith("--port="):
            local_port = _int_or_exit(arg.split("=", 1)[1])
        elif not arg.startswith("-") and name is None:
            name = arg
        i += 1
    return name, local_port


def _int_or_exit(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        print(f"Tunnel can't use port '{value}': not a number.", file=sys.stderr)
        sys.exit(ExitCode.USAGE_ERROR)


def _fetch_endpoint(config: Config, name: str) -> dict:
    """Ask the server for the addon's {type, host, port, url} endpoint."""
    # Deferred imports: pulling rpc at module load creates a circular import
    # (commands.help -> local -> tunnel_cmd -> rpc -> responses -> commands.help).
    from jsonrpcclient import Ok  # noqa: PLC0415

    from hop3_cli.rpc import Client  # noqa: PLC0415

    try:
        with Client(config=config) as client:
            response = client.rpc("cli", ["addon", "endpoint", name])
    except Exception as e:
        print(f"Tunnel can't reach the server: {e}", file=sys.stderr)
        sys.exit(ExitCode.NETWORK_ERROR)

    if not isinstance(response, Ok):
        message = getattr(response, "message", "request failed")
        print(f"Tunnel can't resolve addon '{name}': {message}", file=sys.stderr)
        sys.exit(ExitCode.RESOLUTION_ERROR)

    for item in response.result or []:
        if item.get("t") == "data" and isinstance(item.get("data"), dict):
            payload = item["data"]
            if payload.get("port") and payload.get("url"):
                return payload
    # No endpoint payload: surface the server's own message (e.g. "No addon
    # named X") rather than a generic line that hides the real cause.
    detail = _first_message(response.result or []) or "no endpoint in response"
    print(f"Tunnel can't resolve addon '{name}': {detail}", file=sys.stderr)
    sys.exit(ExitCode.RESOLUTION_ERROR)


def _first_message(items: list) -> str | None:
    """First human-readable message from an RPC item list (error/warning/text)."""
    for item in items:
        if item.get("t") in {"error", "warning", "text"} and item.get("text"):
            return str(item["text"])
    return None


def _ssh_params(config: Config) -> dict:
    """Derive SSH connection parameters from the configured api_url."""
    api_url = config.get_api_url()
    parsed = urlparse(api_url or "")
    if parsed.scheme != "ssh":
        print(
            "Tunnel needs an SSH server connection, but the current server is "
            f"'{api_url}'. Configure an ssh:// server (e.g. "
            "`hop3 settings set server ssh://root@host`).",
            file=sys.stderr,
        )
        sys.exit(ExitCode.USAGE_ERROR)
    return {
        "host": parsed.hostname,
        "user": parsed.username or config.get("ssh_user", "root"),
        "port": parsed.port or config.get("ssh_port", 22),
        "key": config.get("ssh_key", None),
    }


def _start_forwarder(ssh: dict, remote_port: int, bind_port: int):
    """Open the SSH port-forward; fail loud (don't silently re-pick a port)."""
    from sshtunnel import SSHTunnelForwarder  # noqa: PLC0415  (heavy import, defer)

    kwargs = {
        "ssh_username": ssh["user"],
        "ssh_port": ssh["port"],
        "remote_bind_address": ("127.0.0.1", remote_port),
        "local_bind_address": ("127.0.0.1", bind_port),
    }
    if ssh["key"]:
        kwargs["ssh_pkey"] = ssh["key"]

    forwarder = SSHTunnelForwarder(ssh["host"], **kwargs)
    try:
        forwarder.start()
    except Exception as e:
        print(
            f"Tunnel can't bind local port {bind_port}: {e}. "
            "Pick another with `--port <localport>`.",
            file=sys.stderr,
        )
        sys.exit(ExitCode.GENERAL_ERROR)
    return forwarder


def _rewrite_url(url: str, local_port: int) -> str:
    """Rewrite a server-side connection URL to point at the local tunnel."""
    parsed = urlparse(url)
    userinfo = ""
    if parsed.username:
        userinfo = parsed.username
        if parsed.password:
            userinfo += f":{parsed.password}"
        userinfo += "@"
    return urlunparse(parsed._replace(netloc=f"{userinfo}127.0.0.1:{local_port}"))
