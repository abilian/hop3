# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""SSH operations for local commands.

Trust model
-----------
Every input that flows into the shell strings built here (``username``,
``email``, ``ssh_target``, ``hostname``, ``server_url``) originates from
the local user invoking the CLI on their own workstation. The user
already controls their own shell, so there is no privilege boundary
between them and the commands assembled below — "command injection"
into one's own shell is self-injection.

``shlex.quote`` is used here purely for *correctness*: ``ssh_target``
and ``HOP_SERVER_PATH`` are passed to ``ssh`` as a single positional,
which the remote sshd hands to ``$SHELL -c``. Quoting protects against
unusual but legitimate characters in usernames/emails (e.g. apostrophes
in display names), not against an attacker. Do not "fix" this by
replacing the nested ``su -c {shlex.quote(hop3_cmd)}`` pattern with a
list-form call — there is no such form when the transport is a remote
shell.
"""

from __future__ import annotations

import shlex
import subprocess
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from hop3_cli.tokens import extract_jwt

if TYPE_CHECKING:
    from hop3_cli.config import Config

# Path to hop3-server on the remote server
HOP_SERVER_PATH = "/home/hop3/venv/bin/hop3-server"


class BootstrapError(Exception):
    """Error during bootstrap process."""


def create_admin_via_ssh(
    ssh_target: str, username: str, email: str, password: str
) -> str:
    """Create admin user via SSH and return the token.

    Args:
        ssh_target: SSH target (user@host)
        username: Admin username
        email: Admin email
        password: Admin password

    Returns:
        The API token

    Raises:
        BootstrapError: If the command fails
    """
    # Build the remote command - run as hop3 user to ensure correct file ownership
    # The database is created on first access, so running as hop3 ensures it's owned by hop3:hop3
    hop3_cmd = f"{HOP_SERVER_PATH} admin:create {shlex.quote(username)} {shlex.quote(email)} --password-stdin"
    remote_cmd = f"su - hop3 -c {shlex.quote(hop3_cmd)}"

    # Run via SSH
    result = subprocess.run(
        ["ssh", ssh_target, remote_cmd],
        check=False,
        input=password,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        error_msg = result.stderr.strip() or result.stdout.strip() or "Unknown error"
        msg = f"Failed to create admin: {error_msg}"
        raise BootstrapError(msg)

    # Parse token from output
    token = extract_token(result.stdout)
    if not token:
        msg = f"Could not extract token from server response:\n{result.stdout}"
        raise BootstrapError(msg)

    return token


def get_token_via_ssh(ssh_target: str, username: str) -> str:
    """Get a new token for existing user via SSH.

    Args:
        ssh_target: SSH target (user@host)
        username: Username to get token for

    Returns:
        The API token

    Raises:
        BootstrapError: If the command fails
    """
    # Run as hop3 user for consistency and proper file access
    hop3_cmd = f"{HOP_SERVER_PATH} admin:token {shlex.quote(username)}"
    remote_cmd = f"su - hop3 -c {shlex.quote(hop3_cmd)}"

    result = subprocess.run(
        ["ssh", ssh_target, remote_cmd],
        check=False,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        error_msg = result.stderr.strip() or result.stdout.strip() or "Unknown error"
        msg = f"Failed to get token: {error_msg}"
        raise BootstrapError(msg)

    token = extract_token(result.stdout)
    if not token:
        msg = f"Could not extract token from server response:\n{result.stdout}"
        raise BootstrapError(msg)

    return token


def get_ssh_token(ssh_target: str) -> str:
    """Get a token via SSH without needing a username.

    This uses the admin:ssh-token command which:
    - If no users exist: auto-creates a default admin
    - If users exist: returns token for an existing admin

    SSH access is the authentication - no username/password needed.

    Args:
        ssh_target: SSH target (user@host)

    Returns:
        The API token

    Raises:
        BootstrapError: If the command fails
    """
    hop3_cmd = f"{HOP_SERVER_PATH} admin:ssh-token"
    remote_cmd = f"su - hop3 -c {shlex.quote(hop3_cmd)}"

    result = subprocess.run(
        ["ssh", ssh_target, remote_cmd],
        check=False,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        error_msg = result.stderr.strip() or result.stdout.strip() or "Unknown error"
        msg = f"Failed to get SSH token: {error_msg}"
        raise BootstrapError(msg)

    token = extract_token(result.stdout)
    if not token:
        msg = f"Could not extract token from server response:\n{result.stdout}"
        raise BootstrapError(msg)

    return token


def fetch_and_save_certificate(
    ssh_target: str, server_url: str, config: Config
) -> str | None:
    """Fetch the server's SSL certificate via SSH and save it locally.

    Args:
        ssh_target: SSH target (user@host)
        server_url: The HTTPS URL of the server
        config: Config object to determine where to save the certificate

    Returns:
        Path to the saved certificate file, or None if failed
    """
    # Extract hostname from server URL
    parsed = urlparse(server_url)
    hostname = parsed.hostname
    port = parsed.port or 443

    if not hostname:
        return None

    # Use openssl to fetch the certificate via SSH
    # This runs on the server and returns the certificate
    # Use shlex.quote to prevent command injection via crafted hostnames
    remote_cmd = (
        f"openssl s_client -connect {shlex.quote(hostname)}:{port} "
        f"-servername {shlex.quote(hostname)} </dev/null 2>/dev/null | "
        f"openssl x509 2>/dev/null"
    )

    result = subprocess.run(
        ["ssh", ssh_target, remote_cmd],
        check=False,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0 or not result.stdout.strip():
        return None

    cert_content = result.stdout.strip()

    # Validate it looks like a certificate
    if "-----BEGIN CERTIFICATE-----" not in cert_content:
        return None

    # Save the certificate next to the config file
    config_dir = config.config_file.parent if config.config_file else None
    if not config_dir:
        return None

    # Use hostname for the certificate filename
    safe_hostname = hostname.replace(".", "_").replace(":", "_")
    cert_path = config_dir / f"{safe_hostname}.crt"

    # Ensure directory exists
    config_dir.mkdir(parents=True, exist_ok=True)

    # Write the certificate
    cert_path.write_text(cert_content + "\n")

    return str(cert_path)


def extract_token(output: str) -> str | None:
    """Extract JWT token from command output.

    Args:
        output: Command output containing the token

    Returns:
        The JWT token or None if not found
    """
    return extract_jwt(output)


def get_magic_link_via_ssh(ssh_target: str, username: str = "admin") -> str:
    """Get a magic link token via SSH for passwordless web login.

    This calls auth magic-link on the server which generates a short-lived,
    single-use token that can be used to log into the web dashboard.

    Args:
        ssh_target: SSH target (user@host)
        username: Username to generate the magic link for (default: admin)

    Returns:
        The magic link token

    Raises:
        BootstrapError: If the command fails
    """
    hop3_cmd = f"{HOP_SERVER_PATH} auth magic-link {shlex.quote(username)}"
    remote_cmd = f"su - hop3 -c {shlex.quote(hop3_cmd)}"

    result = subprocess.run(
        ["ssh", ssh_target, remote_cmd],
        check=False,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        error_msg = result.stderr.strip() or result.stdout.strip() or "Unknown error"
        msg = f"Failed to generate magic link: {error_msg}"
        raise BootstrapError(msg)

    # The token is returned directly (just the JWT, no extra formatting)
    token = result.stdout.strip()
    if not token:
        msg = "Server returned empty response for magic link"
        raise BootstrapError(msg)

    return token


def infer_server_url(ssh_target: str) -> str:
    """Infer HTTPS URL from SSH target.

    Args:
        ssh_target: SSH target (user@host or host)

    Returns:
        HTTPS URL for the server
    """
    # user@host -> host
    if "@" in ssh_target:
        host = ssh_target.split("@")[1]
    else:
        host = ssh_target

    # Strip SSH port if present
    if ":" in host:
        host = host.split(":")[0]

    return f"https://{host}"
