# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""SSH key management and connectivity utilities."""

from __future__ import annotations

import hashlib
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import paramiko


@dataclass
class SSHConnectionInfo:
    """Information about an SSH connection."""

    host: str
    port: int = 22
    user: str = "root"
    key_path: Path | None = None

    @property
    def address(self) -> str:
        """Return user@host format."""
        return f"{self.user}@{self.host}"


class SSHKeyManager:
    """Manages SSH known_hosts and host key verification."""

    def __init__(self, known_hosts_path: Path | None = None):
        """Initialize SSH key manager.

        Args:
            known_hosts_path: Path to known_hosts file. Defaults to ~/.ssh/known_hosts.
        """
        self.known_hosts_path = known_hosts_path or Path.home() / ".ssh" / "known_hosts"

    def remove_host_key(self, host: str) -> bool:
        """Remove a host's key from known_hosts.

        Args:
            host: Hostname or IP to remove.

        Returns:
            True if key was removed, False if not found.
        """
        if not self.known_hosts_path.exists():
            return False

        # Use ssh-keygen to remove the key
        result = subprocess.run(
            ["ssh-keygen", "-R", host],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    def get_host_key(self, host: str, port: int = 22) -> str | None:
        """Get the SSH host key from a remote server.

        Args:
            host: Hostname or IP address.
            port: SSH port number.

        Returns:
            Host key string or None if unable to retrieve.
        """
        result = subprocess.run(
            ["ssh-keyscan", "-p", str(port), "-t", "ed25519,rsa", host],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return None

    def add_host_key(self, host: str, port: int = 22) -> bool:
        """Scan and add a host's key to known_hosts.

        Args:
            host: Hostname or IP address.
            port: SSH port number.

        Returns:
            True if key was added successfully.
        """
        # Ensure .ssh directory exists
        self.known_hosts_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

        # Use ssh-keyscan with shell redirection to properly append keys
        # This handles multi-line output correctly
        result = subprocess.run(
            f'ssh-keyscan -p {port} -t ed25519,rsa {host} >> {self.known_hosts_path} 2>/dev/null',
            shell=True,
            check=False,
        )
        return result.returncode == 0

    def update_host_key(
        self,
        host: str,
        port: int = 22,
        additional_hosts: list[str] | None = None,
    ) -> bool:
        """Remove old key and add new key for a host.

        Args:
            host: Primary hostname or IP address.
            port: SSH port number.
            additional_hosts: Additional hostnames/aliases to update.

        Returns:
            True if key was updated successfully.
        """
        # Remove old keys for primary host and all aliases
        self.remove_host_key(host)
        for alias in additional_hosts or []:
            self.remove_host_key(alias)

        # Add new key for primary host
        success = self.add_host_key(host, port)

        # For aliases, we need to scan them separately since they may resolve
        # to the same IP but need their own entries
        if success and additional_hosts:
            for alias in additional_hosts:
                self.add_host_key(alias, port)

        return success

    def find_hostnames_for_ip(self, ip_address: str) -> list[str]:
        """Find all hostnames in known_hosts that have the same IP.

        This helps identify aliases that need to be updated when a server
        is rebuilt.

        Args:
            ip_address: IP address to search for.

        Returns:
            List of hostnames that had keys for this IP.
        """
        if not self.known_hosts_path.exists():
            return []

        hostnames = []
        try:
            import socket

            with self.known_hosts_path.open() as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    parts = line.split(None, 1)
                    if not parts:
                        continue

                    host = parts[0]
                    # Skip if it's already the IP
                    if host == ip_address:
                        continue

                    # Try to resolve the hostname
                    try:
                        resolved_ip = socket.gethostbyname(host)
                        if resolved_ip == ip_address:
                            hostnames.append(host)
                    except socket.gaierror:
                        pass

        except Exception:
            pass

        return hostnames

    def get_host_key_fingerprint(self, host: str, port: int = 22) -> str | None:
        """Get the fingerprint of a host's SSH key.

        Args:
            host: Hostname or IP address.
            port: SSH port number.

        Returns:
            SHA256 fingerprint string or None.
        """
        key = self.get_host_key(host, port)
        if not key:
            return None

        # Parse the key and compute fingerprint
        parts = key.split()
        if len(parts) < 2:
            return None

        # The second part is the base64-encoded key
        try:
            import base64

            key_data = base64.b64decode(parts[1])
            digest = hashlib.sha256(key_data).digest()
            fingerprint = base64.b64encode(digest).decode().rstrip("=")
            return f"SHA256:{fingerprint}"
        except Exception:
            return None


class SSHConnection:
    """Manages SSH connections using paramiko."""

    def __init__(self, info: SSHConnectionInfo):
        """Initialize SSH connection.

        Args:
            info: Connection information.
        """
        self.info = info
        self._client: paramiko.SSHClient | None = None

    def connect(self, timeout: int = 30) -> bool:
        """Establish SSH connection.

        Args:
            timeout: Connection timeout in seconds.

        Returns:
            True if connection succeeded.
        """
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            kwargs = {
                "hostname": self.info.host,
                "port": self.info.port,
                "username": self.info.user,
                "timeout": timeout,
            }
            if self.info.key_path:
                kwargs["key_filename"] = str(self.info.key_path)

            self._client.connect(**kwargs)
            return True
        except Exception:
            self._client = None
            return False

    def close(self) -> None:
        """Close SSH connection."""
        if self._client:
            self._client.close()
            self._client = None

    def run(self, command: str, timeout: int = 60) -> tuple[int, str, str]:
        """Execute a command over SSH.

        Args:
            command: Command to execute.
            timeout: Command timeout in seconds.

        Returns:
            Tuple of (exit_code, stdout, stderr).
        """
        if not self._client:
            raise RuntimeError("Not connected")

        stdin, stdout, stderr = self._client.exec_command(command, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        return exit_code, stdout.read().decode(), stderr.read().decode()

    def __enter__(self) -> SSHConnection:
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, *args) -> None:
        """Context manager exit."""
        self.close()


def wait_for_ssh(
    host: str,
    port: int = 22,
    timeout: int = 300,
    interval: int = 10,
) -> bool:
    """Wait for SSH to become available on a host.

    Args:
        host: Hostname or IP address.
        port: SSH port number.
        timeout: Maximum time to wait in seconds.
        interval: Time between connection attempts.

    Returns:
        True if SSH became available, False if timeout.
    """
    deadline = time.time() + timeout

    while time.time() < deadline:
        if is_port_open(host, port):
            # Port is open, try SSH handshake
            try:
                transport = paramiko.Transport((host, port))
                transport.connect()
                transport.close()
                return True
            except Exception:
                pass

        time.sleep(interval)

    return False


def is_port_open(host: str, port: int, timeout: int = 5) -> bool:
    """Check if a TCP port is open.

    Args:
        host: Hostname or IP address.
        port: Port number.
        timeout: Connection timeout in seconds.

    Returns:
        True if port is open.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def verify_ssh_connectivity(
    host: str,
    user: str = "root",
    port: int = 22,
    timeout: int = 30,
) -> bool:
    """Verify SSH connectivity by running a simple command.

    Args:
        host: Hostname or IP address.
        user: SSH username.
        port: SSH port number.
        timeout: Connection timeout.

    Returns:
        True if SSH connection works.
    """
    info = SSHConnectionInfo(host=host, port=port, user=user)
    conn = SSHConnection(info)

    try:
        if not conn.connect(timeout=timeout):
            return False
        exit_code, _, _ = conn.run("echo ok", timeout=10)
        return exit_code == 0
    except Exception:
        return False
    finally:
        conn.close()
