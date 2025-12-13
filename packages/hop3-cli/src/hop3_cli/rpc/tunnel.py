# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""SSH Tunnel implementation for secure remote connections.

**This is currently not used, since we are using the `sshtunnel` package instead.**

Since `sshtunnel` needs paramiko, this implementation is kept for reference and
in case we need to switch back to a custom implementation in the future.
"""

from __future__ import annotations

import socket
import subprocess
import time
from contextlib import closing

from loguru import logger


def find_free_port() -> int:
    """Finds an available local port."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


class SSHTunnel:
    """A class to manage an SSH tunnel subprocess.

    Example Usage:
        remote_db_host = "db.internal.mycompany.com"
        jump_host = "bastion.mycompany.com"
        ssh_user = "myuser"

        with SSHTunnel(remote_host=remote_db_host, remote_port=5432,
                       ssh_host=jump_host, ssh_user=ssh_user) as tunnel:
            print(f"Connecting to remote DB via local port: {tunnel.local_port}")
            # ... use the tunnel to connect to `localhost:tunnel.local_port` ...

        print("Tunnel has been automatically closed.")
    """

    remote_host: str
    remote_port: int
    ssh_host: str
    ssh_user: str
    ssh_key_path: str | None
    local_port: int = -1
    proc: subprocess.Popen | None = None

    def __init__(
        self,
        remote_host: str,
        remote_port: int,
        ssh_host: str,
        ssh_user: str,
        ssh_key_path: str | None = None,
    ):
        """Initializes the SSH tunnel configuration.

        Args:
            remote_host: The final destination host (from the jump host's perspective).
            remote_port: The final destination port.
            ssh_host: The SSH jump host to connect through.
            ssh_user: The username for the SSH jump host.
            ssh_key_path: Path to a specific private SSH key. Defaults to None.
        """
        self.remote_host = remote_host
        self.remote_port = remote_port
        self.ssh_host = ssh_host
        self.ssh_user = ssh_user
        self.ssh_key_path = ssh_key_path

        self.local_port = find_free_port()
        self.proc = None

    def start(self):
        """Starts the SSH tunnel subprocess."""
        if self.proc is not None:
            logger.debug("Tunnel is already running.")
            return

        command = self._build_command()
        logger.debug(f"Starting SSH tunnel with command: {' '.join(command)}")

        self.proc = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        try:
            self._wait_for_ready()
        except (RuntimeError, TimeoutError):
            # Ensure process is cleaned up on failure
            self.stop()
            raise

    def stop(self):
        """Stops the SSH tunnel subprocess."""
        if self.proc:
            logger.debug(f"Stopping SSH tunnel (PID: {self.proc.pid})...")
            self.proc.terminate()  # Send SIGTERM
            try:
                self.proc.wait(timeout=5)  # Wait for graceful shutdown
            except subprocess.TimeoutExpired:
                logger.debug("Tunnel did not terminate gracefully, killing.")
                self.proc.kill()  # Send SIGKILL
            self.proc = None
            logger.debug("Tunnel stopped.")

    def __enter__(self):
        """Context manager entry point."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit point."""
        self.stop()

    def _build_command(self) -> list[str]:
        """Constructs the SSH command as a list of arguments."""
        command = [
            "ssh",
            # -N: Do not execute a remote command
            "-N",
            # -q: Quiet mode
            "-q",
            # Exit if the tunnel can't be established
            "-o",
            "ExitOnForwardFailure=yes",
            # Keep the connection alive
            "-o",
            "ServerAliveInterval=60",
            # Define the local forward
            "-L",
            f"{self.local_port}:{self.remote_host}:{self.remote_port}",
            f"{self.ssh_user}@{self.ssh_host}",
        ]
        if self.ssh_key_path:
            command.extend(["-i", self.ssh_key_path])
        return command

    def _wait_for_ready(self, timeout: int = 10):
        """Waits for the tunnel to become available."""
        start_time = time.monotonic()
        while time.monotonic() - start_time < timeout:
            # Check if the process exited prematurely
            if self.proc is not None and self.proc.poll() is not None:
                stderr_output = ""
                if self.proc.stderr is not None:
                    stderr_output = self.proc.stderr.read().decode(
                        "utf-8", errors="ignore"
                    )
                msg = (
                    f"SSH tunnel process failed to start. "
                    f"Exit code: {self.proc.returncode}. Stderr: {stderr_output.strip()}"
                )
                raise RuntimeError(msg)
            # Try to connect to the local port
            try:
                with socket.create_connection(
                    ("127.0.0.1", self.local_port), timeout=1
                ):
                    logger.debug(
                        f"SSH tunnel to {self.remote_host}:{self.remote_port} "
                        f"is ready on local port {self.local_port}"
                    )
                    return
            except (TimeoutError, ConnectionRefusedError):
                time.sleep(0.1)  # Wait a bit before retrying

        # If the loop finishes, it timed out
        self.stop()
        msg = f"SSH tunnel failed to become ready after {timeout} seconds."
        raise TimeoutError(msg)
