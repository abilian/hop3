# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""SSH key management and connectivity utilities."""

from __future__ import annotations

import base64
import hashlib
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Self

import paramiko


class HostKeyError(RuntimeError):
    """A host's SSH key could not be read into known_hosts."""


@dataclass(frozen=True)
class SSHProbe:
    """Outcome of a connectivity check: truthy when it passed, else why not."""

    ok: bool
    error: str | None = None

    def __bool__(self) -> bool:
        return self.ok


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


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
        """
        Initialize SSH key manager.

        Args:
            known_hosts_path: Path to known_hosts file. Defaults to ~/.ssh/known_hosts.
        """
        self.known_hosts_path = known_hosts_path or Path.home() / ".ssh" / "known_hosts"

    def remove_host_key(self, host: str) -> bool:
        """
        Remove a host's key from known_hosts.

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
        """
        Get the SSH host key from a remote server.

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

    def add_host_key(self, host: str, port: int = 22) -> None:
        """
        Scan and add a host's key to known_hosts.

        Removes any existing key for this host first to avoid duplicates.

        Args:
            host: Hostname or IP address.
            port: SSH port number.

        Raises:
            HostKeyError: ssh-keyscan failed or returned no key. Reported as
                False, it was ignored, and the next ssh failed on the old key.
        """
        # Ensure .ssh directory exists
        self.known_hosts_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

        # Remove existing key first to avoid duplicates
        self.remove_host_key(host)

        # No shell: this used to interpolate host and port into a command
        # string with `>> {path} 2>/dev/null`, which meant a host containing a
        # space or a shell character produced something other than the intended
        # command.
        result = subprocess.run(
            ["ssh-keyscan", "-p", str(port), "-t", "ed25519,rsa", host],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            reason = result.stderr.strip() or "ssh-keyscan returned no host key"
            msg = f"Could not read the host key for {host}:{port}: {reason}"
            raise HostKeyError(msg)

        keys = result.stdout if result.stdout.endswith("\n") else result.stdout + "\n"
        with self.known_hosts_path.open("a") as f:
            f.write(keys)

    def update_host_key(
        self,
        host: str,
        port: int = 22,
        additional_hosts: list[str] | None = None,
    ) -> None:
        """
        Remove old key and add new key for a host.

        Args:
            host: Primary hostname or IP address.
            port: SSH port number.
            additional_hosts: Additional hostnames/aliases to update.

        Raises:
            HostKeyError: a key could not be read, for the host or an alias.
        """
        # Remove old keys for primary host and all aliases
        self.remove_host_key(host)
        for alias in additional_hosts or []:
            self.remove_host_key(alias)

        # Add new key for primary host
        self.add_host_key(host, port)

        # For aliases, we need to scan them separately since they may resolve
        # to the same IP but need their own entries
        for alias in additional_hosts or []:
            self.add_host_key(alias, port)

    def find_hostnames_for_ip(self, ip_address: str) -> list[str]:
        """
        Find all hostnames in known_hosts that have the same IP.

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
        """
        Get the fingerprint of a host's SSH key.

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
            key_data = base64.b64decode(parts[1])
            digest = hashlib.sha256(key_data).digest()
            fingerprint = base64.b64encode(digest).decode().rstrip("=")
            return f"SHA256:{fingerprint}"
        except Exception:
            return None


class SSHConnection:
    """Manages SSH connections using paramiko."""

    def __init__(self, info: SSHConnectionInfo):
        """
        Initialize SSH connection.

        Args:
            info: Connection information.
        """
        self.info = info
        self._client: paramiko.SSHClient | None = None

    def connect(self, timeout: int = 30) -> SSHProbe:
        """
        Establish SSH connection.

        Args:
            timeout: Connection timeout in seconds.

        Returns:
            A passing probe once connected, else the reason it could not.
        """
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            key_filename = str(self.info.key_path) if self.info.key_path else None
            self._client.connect(
                hostname=self.info.host,
                port=self.info.port,
                username=self.info.user,
                timeout=timeout,
                key_filename=key_filename,
            )
        except Exception as e:
            self._client = None
            reason = f"{self.info.address}:{self.info.port}: {_describe(e)}"
            return SSHProbe(ok=False, error=reason)
        return SSHProbe(ok=True)

    def close(self) -> None:
        """Close SSH connection."""
        if self._client:
            self._client.close()
            self._client = None

    def run(self, command: str, timeout: int = 60) -> tuple[int, str, str]:
        """
        Execute a command over SSH.

        Args:
            command: Command to execute.
            timeout: Command timeout in seconds.

        Returns:
            Tuple of (exit_code, stdout, stderr).
        """
        if not self._client:
            msg = "Not connected"
            raise RuntimeError(msg)

        _stdin, stdout, stderr = self._client.exec_command(command, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        return exit_code, stdout.read().decode(), stderr.read().decode()

    def __enter__(self) -> Self:
        """Context manager entry; raises when the connection fails."""
        if not (probe := self.connect()):
            msg = f"SSH connection failed: {probe.error}"
            raise ConnectionError(msg)
        return self

    def __exit__(self, *args) -> None:
        """Context manager exit."""
        self.close()


def wait_for_ssh(
    host: str,
    port: int = 22,
    timeout: int = 300,
    interval: int = 10,
) -> SSHProbe:
    """
    Wait for SSH to become available on a host.

    Args:
        host: Hostname or IP address.
        port: SSH port number.
        timeout: Maximum time to wait in seconds.
        interval: Time between connection attempts.

    Returns:
        A passing probe once the SSH handshake succeeds; on timeout, a failing
        probe carrying the last attempt's error.
    """
    deadline = time.time() + timeout
    last = SSHProbe(ok=False, error=f"no attempt made within {timeout}s")

    while time.time() < deadline:
        last = is_port_open(host, port)
        if last:
            # Port is open, try SSH handshake
            try:
                transport = paramiko.Transport((host, port))
                transport.connect()
                transport.close()
                return SSHProbe(ok=True)
            except Exception as e:
                last = SSHProbe(ok=False, error=f"SSH handshake: {_describe(e)}")

        time.sleep(interval)

    return SSHProbe(
        ok=False,
        error=f"SSH on {host}:{port} not ready after {timeout}s ({last.error})",
    )


def is_port_open(host: str, port: int, timeout: int = 5) -> SSHProbe:
    """
    Check if a TCP port is open.

    Args:
        host: Hostname or IP address.
        port: Port number.
        timeout: Connection timeout in seconds.

    Returns:
        A passing probe if the port accepts a connection, else the reason.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return SSHProbe(ok=True)
    except OSError as e:
        return SSHProbe(ok=False, error=f"TCP {host}:{port}: {_describe(e)}")


def verify_ssh_connectivity(
    host: str,
    user: str = "root",
    port: int = 22,
    timeout: int = 30,
) -> SSHProbe:
    """
    Verify SSH connectivity by running a simple command.

    Args:
        host: Hostname or IP address.
        user: SSH username.
        port: SSH port number.
        timeout: Connection timeout.

    Returns:
        A passing probe if `echo ok` ran, else the reason.
    """
    info = SSHConnectionInfo(host=host, port=port, user=user)
    conn = SSHConnection(info)

    try:
        if not (connected := conn.connect(timeout=timeout)):
            return connected
        exit_code, _, stderr = conn.run("echo ok", timeout=10)
        if exit_code != 0:
            return SSHProbe(
                ok=False, error=f"`echo ok` exited {exit_code}: {stderr.strip()}"
            )
        return SSHProbe(ok=True)
    except Exception as e:
        return SSHProbe(ok=False, error=_describe(e))
    finally:
        conn.close()
