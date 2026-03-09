# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Hetzner Cloud API integration for server management."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from hcloud import Client
from hcloud.images import Image
from hcloud.servers import Server

from .ssh import SSHKeyManager, wait_for_ssh

if TYPE_CHECKING:
    from .config import HetznerConfig


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
    datacenter: str
    server_type: str
    image: str | None

    @classmethod
    def from_server(cls, server: Server) -> ServerInfo:
        """Create from hcloud Server object."""
        return cls(
            id=server.id,
            name=server.name,
            status=ServerStatus(server.status)
            if server.status
            else ServerStatus.UNKNOWN,
            ipv4=server.public_net.ipv4.ip if server.public_net.ipv4 else "",
            ipv6=server.public_net.ipv6.ip if server.public_net.ipv6 else None,
            datacenter=server.datacenter.name if server.datacenter else "",
            server_type=server.server_type.name if server.server_type else "",
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

    def __init__(self, config: HetznerConfig):
        """Initialize Hetzner manager.

        Args:
            config: Hetzner configuration.
        """
        self.config = config
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

        Returns:
            IPv4 address string.
        """
        return self.get_server_info().ipv4

    def rebuild_server(
        self,
        image: str | None = None,
        timeout: int = 600,
    ) -> ServerInfo:
        """Rebuild the server with a fresh OS image.

        This is the cleanest way to reset a server - it reinstalls the OS
        completely, removing all data and resetting SSH host keys.

        Args:
            image: OS image name (e.g., "debian-12"). Uses config default if None.
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

        # Get SSH key if configured
        ssh_keys = None
        if self.config.ssh_key_name:
            ssh_key = self._client.ssh_keys.get_by_name(self.config.ssh_key_name)
            if ssh_key:
                ssh_keys = [ssh_key]

        # Initiate rebuild
        response = self._client.servers.rebuild(
            server,
            image=image_obj,
            ssh_keys=ssh_keys,
        )

        if not response.action:
            msg = "Rebuild action not started"
            raise ServerResetError(msg)

        # Wait for action to complete
        self._wait_for_action(response.action.id, timeout=timeout)

        # Update SSH known_hosts with new host key
        server_ip = self.get_server_ip()

        # Find any hostname aliases that resolve to this IP
        aliases = self._ssh_key_manager.find_hostnames_for_ip(server_ip)

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
            name: Image name (e.g., "debian-12").

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
    ) -> None:
        """Wait for an action to complete.

        Args:
            action_id: Action ID to wait for.
            timeout: Maximum time to wait in seconds.
            interval: Time between status checks.

        Raises:
            ServerResetError: If action fails or times out.
        """
        deadline = time.time() + timeout

        while time.time() < deadline:
            action = self._client.actions.get_by_id(action_id)

            if not action:
                msg = f"Action {action_id} not found"
                raise ServerResetError(msg)

            if action.status == "success":
                return

            if action.status == "error":
                msg = f"Action {action_id} failed: {action.error}"
                raise ServerResetError(msg)

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
