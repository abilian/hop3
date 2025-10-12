# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Remote server deployment target (SSH-based)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import paramiko

from .base import DeploymentTarget, TargetInfo

if TYPE_CHECKING:
    from collections.abc import Iterator


class RemoteTarget(DeploymentTarget):
    """Remote server deployment target.

    This target connects to an existing Hop3 server via SSH for testing.
    It can be used for VMs, remote servers, or any SSH-accessible Hop3 installation.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """Initialize remote target.

        Args:
            config: Configuration dictionary with required keys:
                - host: SSH hostname or IP
                - port: SSH port (default: 22)
                - user: SSH username (default: "hop3")
                - ssh_key: Path to SSH key file (optional)
                - password: SSH password (optional, if no key)
                - http_base: Base URL for HTTP access (optional)
                - api_url: Hop3 API URL (optional)
        """
        super().__init__(config)

        if not config:
            msg = "RemoteTarget requires configuration"
            raise ValueError(msg)

        # Required configuration
        if "host" not in config:
            msg = "RemoteTarget requires 'host' in configuration"
            raise ValueError(msg)

        self.host = config["host"]
        self.port = config.get("port", 22)
        self.user = config.get("user", "hop3")
        self.ssh_key_path = config.get("ssh_key")
        self.password = config.get("password")

        # Optional configuration
        self.http_base = config.get("http_base", f"http://{self.host}")
        self.api_url = config.get("api_url", f"http://{self.host}:8000")

        # SSH client
        self.ssh_client: paramiko.SSHClient | None = None

    def start(self) -> TargetInfo:
        """Connect to the remote server.

        Returns:
            TargetInfo with connection details
        """
        print("\n" + "=" * 60)
        print(f"Connecting to remote Hop3 server at {self.host}:{self.port}...")
        print("=" * 60)

        # Create SSH client
        self.ssh_client = paramiko.SSHClient()
        self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Connect with modern ciphers only (no deprecated TripleDES)
        connect_kwargs: dict[str, Any] = {
            "hostname": self.host,
            "port": self.port,
            "username": self.user,
            # Prefer modern ciphers, disable deprecated ones
            "disabled_algorithms": {
                "ciphers": ["3des-cbc"],  # Disable TripleDES
            },
        }

        if self.ssh_key_path:
            connect_kwargs["key_filename"] = self.ssh_key_path
        elif self.password:
            connect_kwargs["password"] = self.password
        else:
            msg = "Either ssh_key or password must be provided"
            raise ValueError(msg)

        try:
            self.ssh_client.connect(**connect_kwargs)
            print(f"✓ Connected to {self.user}@{self.host}:{self.port}")
        except Exception as e:
            msg = f"Failed to connect to remote server: {e}"
            raise RuntimeError(msg) from e

        # Check if server is ready
        if not self.is_ready():
            msg = "Remote server is not ready (hop3-server not responding)"
            raise RuntimeError(msg)

        # Create target info
        self._info = TargetInfo(
            ssh_host=f"{self.user}@{self.host}",
            ssh_port=self.port,
            ssh_key=self.ssh_key_path,
            ssh_password=self.password,
            http_base=self.http_base,
            api_url=self.api_url,
            metadata={
                "host": self.host,
                "user": self.user,
            },
        )

        print("\nRemote target ready:")
        print(f"  SSH: ssh -p {self.port} {self.user}@{self.host}")
        print(f"  HTTP: {self.http_base}")
        print(f"  API: {self.api_url}")
        print("=" * 60 + "\n")

        return self._info

    def stop(self) -> None:
        """Disconnect from the remote server."""
        if self.ssh_client:
            print("\nDisconnecting from remote server...")
            self.ssh_client.close()
            self.ssh_client = None
            print("Disconnected.")

    def is_ready(self) -> bool:
        """Check if the remote server is ready.

        Returns:
            True if server is responding, False otherwise
        """
        if not self.ssh_client:
            return False

        try:
            # Check if hop3-server is responding
            _stdin, stdout, _stderr = self.ssh_client.exec_command(
                "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/ || echo '000'"
            )
            output = stdout.read().decode().strip()
            return output in {"200", "404"}
        except Exception:
            return False

    def exec_run(self, cmd: str | list[str]) -> tuple[int, str, str]:
        """Execute a command on the remote server.

        Args:
            cmd: Command to execute

        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        if not self.ssh_client:
            msg = "Not connected to remote server"
            raise RuntimeError(msg)

        if isinstance(cmd, list):
            # Properly escape command arguments
            cmd = " ".join(f'"{arg}"' if " " in arg else arg for arg in cmd)

        try:
            _stdin, stdout, stderr = self.ssh_client.exec_command(cmd)
            exit_code = stdout.channel.recv_exit_status()
            stdout_text = stdout.read().decode()
            stderr_text = stderr.read().decode()

            return exit_code, stdout_text, stderr_text
        except Exception as e:
            msg = f"Failed to execute command: {e}"
            raise RuntimeError(msg) from e

    def get_logs(self) -> Iterator[str]:
        """Get logs from the remote server.

        Yields:
            Log lines
        """
        if not self.ssh_client:
            return

        # Try to get hop3-server logs
        try:
            _stdin, stdout, _stderr = self.ssh_client.exec_command(
                "tail -n 100 /var/log/hop3-server.log 2>/dev/null || "
                "journalctl -u hop3-server -n 100 --no-pager 2>/dev/null || "
                "echo 'No logs available'"
            )
            for line in stdout:
                yield line.rstrip("\n")
        except Exception as e:
            yield f"Error getting logs: {e}"

    @classmethod
    def from_env(cls, env_prefix: str = "HOP3_TEST") -> RemoteTarget:
        """Create a RemoteTarget from environment variables.

        Args:
            env_prefix: Prefix for environment variables (default: "HOP3_TEST")

        Environment variables:
            - {prefix}_HOST: Server hostname
            - {prefix}_PORT: SSH port (default: 22)
            - {prefix}_USER: SSH username (default: "hop3")
            - {prefix}_SSH_KEY: Path to SSH key
            - {prefix}_PASSWORD: SSH password
            - {prefix}_HTTP_BASE: Base HTTP URL
            - {prefix}_API_URL: API URL

        Returns:
            RemoteTarget instance
        """
        import os

        config = {}

        # Required
        host = os.getenv(f"{env_prefix}_HOST")
        if not host:
            msg = f"Environment variable {env_prefix}_HOST is required"
            raise ValueError(msg)
        config["host"] = host

        # Optional
        if port := os.getenv(f"{env_prefix}_PORT"):
            config["port"] = int(port)

        if user := os.getenv(f"{env_prefix}_USER"):
            config["user"] = user

        if ssh_key := os.getenv(f"{env_prefix}_SSH_KEY"):
            config["ssh_key"] = ssh_key

        if password := os.getenv(f"{env_prefix}_PASSWORD"):
            config["password"] = password

        if http_base := os.getenv(f"{env_prefix}_HTTP_BASE"):
            config["http_base"] = http_base

        if api_url := os.getenv(f"{env_prefix}_API_URL"):
            config["api_url"] = api_url

        return cls(config)
