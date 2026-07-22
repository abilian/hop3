# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Hetzner Cloud API integration for server management."""

from __future__ import annotations

import base64
import hashlib
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from hcloud import Client

from hop3_testing.util.ssh import SSHKeyManager, wait_for_ssh

if TYPE_CHECKING:
    from hcloud.images import Image
    from hcloud.servers import Server
    from rich.console import Console

    from .config import HetznerConfig


def _public_key_md5_fingerprint(key_path: str | Path) -> str | None:
    """MD5 fingerprint (colon-hex) of the public half of ``key_path``.

    Matches the ``.fingerprint`` Hetzner reports for a registered SSH key, so a
    local private key can be mapped to its registered counterpart by reading the
    ``<key_path>.pub`` sibling. None if the .pub is missing or unparseable.
    """
    pub = Path(f"{key_path}.pub")
    try:
        parts = pub.read_text(encoding="utf-8").split()
    except OSError:
        return None
    if len(parts) < 2:  # expect: "<type> <base64-blob> [comment]"
        return None
    try:
        blob = base64.b64decode(parts[1])
    except ValueError:  # binascii.Error subclasses ValueError
        return None
    return ":".join(f"{b:02x}" for b in hashlib.md5(blob).digest())


class ServerStatus(Enum):
    """Server status enumeration."""

    RUNNING = "running"
    OFF = "off"
    STARTING = "starting"
    STOPPING = "stopping"
    REBUILDING = "rebuilding"
    UNKNOWN = "unknown"


@dataclass
class ServerInfo:
    """Information about a Hetzner server."""

    id: int
    name: str
    status: ServerStatus
    ipv4: str
    ipv6: str | None
    # Hetzner deprecated datacenters on 2026-06-02 (removal after 2026-10-01)
    # and hcloud 2.23 dropped `Server.datacenter` accordingly. Location is the
    # replacement: coarser (hel1 rather than hel1-dc2), and the field that
    # exists.
    location: str
    server_type: str
    image: str | None

    @classmethod
    def from_server(cls, server: Server) -> ServerInfo:
        """Create from hcloud Server object."""
        # Extract IPv4/IPv6 with proper null checks
        ipv4 = ""
        ipv6 = None
        if server.public_net and server.public_net.ipv4:
            ipv4 = server.public_net.ipv4.ip or ""
        if server.public_net and server.public_net.ipv6:
            ipv6 = server.public_net.ipv6.ip

        return cls(
            id=server.id or 0,
            name=server.name or "",
            status=ServerStatus(server.status)
            if server.status
            else ServerStatus.UNKNOWN,
            ipv4=ipv4,
            ipv6=ipv6,
            location=(server.location.name or "") if server.location else "",
            server_type=(server.server_type.name or "") if server.server_type else "",
            image=server.image.name if server.image else None,
        )


class HetznerError(Exception):
    """Base exception for Hetzner operations."""


class ServerNotFoundError(HetznerError):
    """Server not found."""


class ServerResetError(HetznerError):
    """Failed to reset server."""


class HetznerManager:
    """Manages Hetzner Cloud servers for testing."""

    def __init__(
        self,
        config: HetznerConfig,
        verbose: bool = False,
        console: Console | None = None,
    ):
        """Initialize Hetzner manager.

        Args:
            config: Hetzner configuration.
            verbose: Enable verbose output.
            console: Rich console for output.
        """
        self.config = config
        self.verbose = verbose
        self.console = console
        self._client = Client(token=config.api_token)
        self._ssh_key_manager = SSHKeyManager()

    @property
    def server_id(self) -> int:
        """Get configured server ID."""
        return self.config.server_id

    def get_server(self) -> Server:
        """Get the configured server.

        Returns:
            Server object.

        Raises:
            ServerNotFoundError: If server not found.
        """
        server = self._client.servers.get_by_id(self.server_id)
        if not server:
            msg = f"Server {self.server_id} not found"
            raise ServerNotFoundError(msg)
        return server

    def get_server_info(self) -> ServerInfo:
        """Get information about the configured server.

        Returns:
            ServerInfo object.
        """
        return ServerInfo.from_server(self.get_server())

    def get_server_ip(self) -> str:
        """Get the server's IPv4 address.

        Reads the address off the server directly rather than through
        ``ServerInfo``: the rebuild path needs only the IP, and mapping every
        other field first makes an unrelated upstream model change (hcloud
        removing ``Server.datacenter``) abort the provisioning run.

        Returns:
            IPv4 address string.
        """
        server = self.get_server()
        if not (server.public_net and server.public_net.ipv4):
            msg = f"Server {self.server_id} has no public IPv4 address"
            raise HetznerError(msg)
        return server.public_net.ipv4.ip or ""

    def list_images(self) -> list[dict]:
        """List available OS images.

        Returns:
            List of image dictionaries with 'name' and 'description' keys.
        """
        images = self._client.images.get_all()
        return [
            {
                "name": img.name,
                "description": img.description or "",
                "type": img.type,
            }
            for img in images
            if img.type == "system"  # Only show system images, not snapshots/backups
        ]

    def resolve_ssh_key(self):
        """The registered Hetzner SSH key to re-inject on rebuild, or raise loud.

        Order: explicit ``ssh_key_name`` (must exist in the project); otherwise
        auto-derive from ``ssh_key_path`` by matching ``<path>.pub``'s
        fingerprint against the project's registered keys. Never returns None —
        a rebuild with no key locks us out, so an unresolvable key is a hard,
        explained error rather than a silent skip.
        """
        name = self.config.ssh_key_name
        if name:
            key = self._client.ssh_keys.get_by_name(name)
            if key is None:
                msg = (
                    f"hetzner.ssh_key_name={name!r} is not a key registered in "
                    f"your Hetzner project, so the rebuild would lock us out. "
                    f"Check `hcloud ssh-key list`, or fix the name."
                )
                raise ServerResetError(msg)
            return key

        key_path = self.config.ssh_key_path
        if not key_path:
            msg = (
                "Can't determine which SSH key to re-inject on rebuild — a "
                "rebuild with no key locks us out of the server. Set one of:\n"
                "  - hetzner.ssh_key_name (or env HETZNER_SSH_KEY_NAME): the name "
                "of an SSH key already registered in your Hetzner project "
                "(`hcloud ssh-key list`); or\n"
                "  - hetzner.ssh_key_path (or env HETZNER_SSH_KEY_PATH): path to a "
                "private key whose <path>.pub is registered there (its fingerprint "
                "is matched against the project)."
            )
            raise ServerResetError(msg)

        fingerprint = _public_key_md5_fingerprint(key_path)
        if fingerprint is None:
            msg = (
                f"Can't read {key_path}.pub to auto-derive the Hetzner SSH key. "
                f"Ensure the public key exists, or set hetzner.ssh_key_name."
            )
            raise ServerResetError(msg)

        for key in self._client.ssh_keys.get_all():
            if key.fingerprint == fingerprint:
                return key

        msg = (
            f"Your key {key_path}.pub (fingerprint {fingerprint}) is not "
            f"registered in your Hetzner project, so the rebuilt server would "
            f"have no SSH access. Upload it — `hcloud ssh-key create --name "
            f"<name> --public-key-from-file {key_path}.pub` — or set "
            f"hetzner.ssh_key_name."
        )
        raise ServerResetError(msg)

    def rebuild_server(
        self,
        image: str | None = None,
        timeout: int = 600,
    ) -> ServerInfo:
        """Rebuild the server with a fresh OS image.

        This is the cleanest way to reset a server - it reinstalls the OS
        completely, removing all data and resetting SSH host keys.

        Args:
            image: OS image name (e.g., "debian-13"). Uses config default if None.
            timeout: Maximum time to wait for rebuild in seconds.

        Returns:
            Updated ServerInfo after rebuild.

        Raises:
            ServerResetError: If rebuild fails.
        """
        image_name = image or self.config.image
        server = self.get_server()

        # Find the image
        image_obj = self._find_image(image_name)
        if not image_obj:
            msg = f"Image '{image_name}' not found"
            raise ServerResetError(msg)

        # Resolve the SSH key to re-inject (raises loud if it can't — a rebuild
        # with no key would lock us out of the fresh OS).
        ssh_key = self.resolve_ssh_key()

        # Initiate rebuild
        response = self._client.servers.rebuild(
            server,
            image=image_obj,
            ssh_keys=[ssh_key],
        )

        if not response.action:
            msg = "Rebuild action not started"
            raise ServerResetError(msg)

        # Wait for action to complete
        if self.verbose and self.console:
            self.console.print(f"    Rebuild started (action {response.action.id})")
        self._wait_for_action(
            response.action.id, timeout=timeout, action_name="rebuild"
        )

        # Update SSH known_hosts with new host key
        server_ip = self.get_server_ip()
        if self.verbose and self.console:
            self.console.print(f"    Updating SSH known_hosts for {server_ip}")

        # Find any hostname aliases that resolve to this IP
        aliases = self._ssh_key_manager.find_hostnames_for_ip(server_ip)
        if self.verbose and self.console and aliases:
            self.console.print(f"    Found aliases: {', '.join(aliases)}")

        # Update known_hosts for IP and all aliases
        self._ssh_key_manager.update_host_key(server_ip, additional_hosts=aliases)

        return self.get_server_info()

    def reset_server(
        self,
        timeout: int = 120,
    ) -> ServerInfo:
        """Perform a soft reset (reboot) of the server.

        This is faster than rebuild but doesn't reinstall the OS.

        Args:
            timeout: Maximum time to wait for reset in seconds.

        Returns:
            Updated ServerInfo after reset.
        """
        server = self.get_server()

        response = self._client.servers.reset(server)

        if response.action:
            self._wait_for_action(response.action.id, timeout=timeout)

        return self.get_server_info()

    def power_on(self, timeout: int = 60) -> ServerInfo:
        """Power on the server.

        Args:
            timeout: Maximum time to wait in seconds.

        Returns:
            Updated ServerInfo.
        """
        server = self.get_server()

        if server.status == "running":
            return self.get_server_info()

        response = self._client.servers.power_on(server)

        if response.action:
            self._wait_for_action(response.action.id, timeout=timeout)

        return self.get_server_info()

    def power_off(self, timeout: int = 60) -> ServerInfo:
        """Power off the server (hard shutdown).

        Args:
            timeout: Maximum time to wait in seconds.

        Returns:
            Updated ServerInfo.
        """
        server = self.get_server()

        if server.status == "off":
            return self.get_server_info()

        response = self._client.servers.power_off(server)

        if response.action:
            self._wait_for_action(response.action.id, timeout=timeout)

        return self.get_server_info()

    def shutdown(self, timeout: int = 120) -> ServerInfo:
        """Graceful shutdown of the server.

        Args:
            timeout: Maximum time to wait in seconds.

        Returns:
            Updated ServerInfo.
        """
        server = self.get_server()

        if server.status == "off":
            return self.get_server_info()

        response = self._client.servers.shutdown(server)

        if response.action:
            self._wait_for_action(response.action.id, timeout=timeout)

        return self.get_server_info()

    def wait_for_ssh_ready(
        self,
        timeout: int = 300,
        interval: int = 10,
    ) -> bool:
        """Wait for SSH to become available on the server.

        Also updates the known_hosts file with the server's host key.

        Args:
            timeout: Maximum time to wait in seconds.
            interval: Time between connection attempts.

        Returns:
            True if SSH is ready, False if timeout.
        """
        server_ip = self.get_server_ip()

        # Wait for SSH port to be open and responsive
        if not wait_for_ssh(server_ip, timeout=timeout, interval=interval):
            return False

        # Find any hostname aliases that resolve to this IP
        aliases = self._ssh_key_manager.find_hostnames_for_ip(server_ip)

        # Update known_hosts for IP and all aliases
        self._ssh_key_manager.update_host_key(server_ip, additional_hosts=aliases)

        return True

    def _find_image(self, name: str) -> Image | None:
        """Find an image by name.

        Args:
            name: Image name (e.g., "debian-13").

        Returns:
            Image object or None if not found.
        """
        images = self._client.images.get_all(name=name)
        if images:
            return images[0]

        # Try searching by description
        all_images = self._client.images.get_all()
        for image in all_images:
            if name in (image.name or "") or name in (image.description or ""):
                return image

        return None

    def _wait_for_action(
        self,
        action_id: int,
        timeout: int = 300,
        interval: int = 5,
        action_name: str = "action",
    ) -> None:
        """Wait for an action to complete.

        Args:
            action_id: Action ID to wait for.
            timeout: Maximum time to wait in seconds.
            interval: Time between status checks.
            action_name: Name of action for progress messages.

        Raises:
            ServerResetError: If action fails or times out.
        """
        deadline = time.time() + timeout
        start_time = time.time()
        last_progress = -1

        while time.time() < deadline:
            action = self._client.actions.get_by_id(action_id)

            if not action:
                msg = f"Action {action_id} not found"
                raise ServerResetError(msg)

            if action.status == "success":
                if self.verbose and self.console:
                    elapsed = int(time.time() - start_time)
                    self.console.print(f"    [{elapsed}s] {action_name} completed")
                return

            if action.status == "error":
                msg = f"Action {action_id} failed: {action.error}"
                raise ServerResetError(msg)

            # Show progress in verbose mode
            elapsed = int(time.time() - start_time)
            progress = (action.progress or 0) if hasattr(action, "progress") else 0
            if self.verbose and self.console and progress != last_progress:
                self.console.print(
                    f"    [{elapsed}s] {action_name}: {action.status} ({progress}%)"
                )
                last_progress = progress
            elif (
                not self.verbose and self.console and elapsed % 30 == 0 and elapsed > 0
            ):
                # Brief update every 30s in non-verbose mode
                self.console.print(f" ({elapsed}s)", end="")

            time.sleep(interval)

        msg = f"Action {action_id} timed out after {timeout}s"
        raise ServerResetError(msg)


def create_hetzner_manager(config: HetznerConfig) -> HetznerManager:
    """Create a HetznerManager instance.

    Factory function for dependency injection.

    Args:
        config: Hetzner configuration.

    Returns:
        HetznerManager instance.
    """
    return HetznerManager(config)
