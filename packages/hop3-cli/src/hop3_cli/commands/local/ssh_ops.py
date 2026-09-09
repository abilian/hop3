# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
SSH operations for local commands.

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

from hop3_cli.config import get_config
from hop3_cli.core.ssh_target import (
    SshSettings,
    is_safe_ssh_target,
    split_ssh_target,
    ssh_base_argv,
)
from hop3_cli.tokens import extract_jwt

if TYPE_CHECKING:
    from hop3_cli.config import Config

# Path to hop3-server on the remote server
HOP_SERVER_PATH = "/home/hop3/venv/bin/hop3-server"

# Default HTTP port the hop3-server ASGI app binds to. Used to build the
# magic-link URL when the server has no public admin domain (so the dashboard
# is reachable only on the app port, not via nginx/TLS on 443).
DEFAULT_WEB_PORT = 8000


class BootstrapError(Exception):
    """Error during bootstrap process."""


def validate_ssh_target(ssh_target: str) -> None:
    """
    Reject an ssh target that could inject SSH options (audit M1).

    ``ssh_target`` is passed as a positional to ``ssh``. A value beginning with
    ``-`` — e.g. built from ``ssh://-oProxyCommand=evil@host`` — is parsed by
    ssh as an *option*, enabling ``ProxyCommand`` arbitrary command execution.
    Since we only ever construct ``user@host`` targets, a leading ``-``, an
    empty host, or shell metacharacters are always malformed input.

    Raises:
        BootstrapError: if ``ssh_target`` is not a plain ``[user@]host[:port]``.
    """
    if not is_safe_ssh_target(ssh_target):
        msg = (
            f"Refusing unsafe SSH target {ssh_target!r}: expected a plain "
            f"user@host (no leading '-' or special characters)."
        )
        raise BootstrapError(msg)
    try:
        split_ssh_target(ssh_target)
    except ValueError as e:
        raise BootstrapError(str(e)) from e


def _run_ssh(
    ssh_target: str, remote_cmd: str, *, input: str | None = None
) -> subprocess.CompletedProcess[str]:
    """
    Run ``ssh <target> <remote_cmd>``, validating the target first.

    Single choke point for every ssh invocation in this module so target
    validation (against SSH option injection, audit M1) happens exactly once
    instead of being duplicated at each call site.
    """
    return subprocess.run(
        ssh_command_argv(ssh_target, remote_cmd),
        check=False,
        input=input,
        capture_output=True,
        text=True,
    )


def ssh_command_argv(ssh_target: str, remote_cmd: str) -> list[str]:
    """
    The ``ssh`` command line for one remote command, from the CLI's settings.

    The target may carry a port (``root@host:2222``): a server on a
    non-standard SSH port was reachable through the ``ssh://`` tunnel and not
    through ``login --ssh``, which ran a bare ``ssh user@host``. The key
    (``ssh_key``) and the extra options (``ssh_options``) are the same
    settings the tunnel honours, so the bootstrap and the transport it sets up
    reach the same box the same way; new host keys are accepted as the tunnel
    accepts them.
    """
    validate_ssh_target(ssh_target)
    user_host, port = split_ssh_target(ssh_target)
    settings = SshSettings.from_config(get_config())
    return [*ssh_base_argv(settings, port=port), user_host, remote_cmd]


def _ssh_user(ssh_target: str) -> str:
    """The account the SSH connection runs as; bare hosts default to root."""
    return ssh_target.split("@", maxsplit=1)[0] if "@" in ssh_target else "root"


def refuse_hop3_ssh_user(ssh_target: str) -> None:
    """
    Refuse ``hop3@host`` before dialling it.

    That account's key carries a forced command in ``~hop3/.ssh/authorized_keys``
    which prepends ``hop3-server`` to whatever it is given (the path `git push`
    and `app shell` take). Everything below sends ``su - hop3 -c '…'``, so the
    remote line becomes ``hop3-server su - hop3 -c '…'`` and fails with a
    baffling complaint about an unknown `su` command. Say what is wrong instead.
    """
    if _ssh_user(ssh_target) != "hop3":
        return
    host = _host_from_ssh_target(ssh_target)
    msg = (
        f"Hop3 can't bootstrap through the 'hop3' account on {host}.\n"
        f"\n"
        f"That account's SSH key is the deploy key: its forced command runs "
        f"hop3-server\nfor you, so it cannot run the admin command this needs. "
        f"Connect as root:\n"
        f"\n"
        f"  hop3 login --ssh root@{host}"
    )
    raise BootstrapError(msg)


def _run_hop3_server(
    ssh_target: str, hop3_cmd: str, action: str, *, input: str | None = None
) -> str:
    """
    Run one ``hop3-server`` command as the server's ``hop3`` user, over SSH.

    Single choke point for the four bootstrap operations. Each used to repeat
    the same three lines and surface ``su``'s own message verbatim, so a
    perfectly ordinary mistake — connecting as a non-root admin account —
    reported "Failed to get SSH token: su: Authentication failure" and left the
    operator to work out that root is the requirement.
    """
    refuse_hop3_ssh_user(ssh_target)
    remote_cmd = f"su - hop3 -c {shlex.quote(hop3_cmd)}"
    result = _run_ssh(ssh_target, remote_cmd, input=input)
    if result.returncode != 0:
        raise BootstrapError(_bootstrap_failure(ssh_target, remote_cmd, result, action))
    return result.stdout


def _bootstrap_failure(
    ssh_target: str,
    remote_cmd: str,
    result: subprocess.CompletedProcess[str],
    action: str,
) -> str:
    """
    Name the input, the command run, its output, and the way forward.

    The root requirement is stated whenever the SSH user is not root, rather
    than pattern-matched out of ``su``'s wording: the connecting account is
    something we know for certain, and scraping a tool's prose to decide what
    to advise is how the advice goes stale.
    """
    output = result.stderr.strip() or result.stdout.strip() or "(no output)"
    host = _host_from_ssh_target(ssh_target)
    user = _ssh_user(ssh_target)
    lines = [
        f"Hop3 can't {action} on {host} as {user!r}.",
        "",
        f"  ran:  ssh {ssh_target} {remote_cmd}",
        f"  got:  {output}",
    ]
    if user != "root":
        lines += [
            "",
            "This runs one command as the server's 'hop3' account, which needs",
            "root. Connect as root:",
            "",
            f"  hop3 login --ssh root@{host}",
        ]
    return "\n".join(lines)


def create_admin_via_ssh(
    ssh_target: str, username: str, email: str, password: str
) -> str:
    """
    Create admin user via SSH and return the token.

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
    # Run as the hop3 user so the database it creates on first access is owned
    # by hop3:hop3 rather than root.
    hop3_cmd = (
        f"{HOP_SERVER_PATH} admin:create "
        f"{shlex.quote(username)} {shlex.quote(email)} --password-stdin"
    )
    stdout = _run_hop3_server(
        ssh_target, hop3_cmd, "create an admin user", input=password
    )
    return _require_token(stdout)


def get_token_via_ssh(ssh_target: str, username: str) -> str:
    """
    Get a new token for existing user via SSH.

    Args:
        ssh_target: SSH target (user@host)
        username: Username to get token for

    Returns:
        The API token

    Raises:
        BootstrapError: If the command fails
    """
    hop3_cmd = f"{HOP_SERVER_PATH} admin:token {shlex.quote(username)}"
    stdout = _run_hop3_server(ssh_target, hop3_cmd, f"issue a token for {username!r}")
    return _require_token(stdout)


def get_ssh_token(ssh_target: str) -> str:
    """
    Get a token via SSH without needing a username.

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
    stdout = _run_hop3_server(ssh_target, hop3_cmd, "sign in")
    return _require_token(stdout)


def fetch_and_save_certificate(
    ssh_target: str, server_url: str, config: Config
) -> str | None:
    """
    Fetch the server's SSL certificate via SSH and save it locally.

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

    result = _run_ssh(ssh_target, remote_cmd)

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


def _require_token(stdout: str) -> str:
    """The JWT in a bootstrap command's output, or a loud failure."""
    token = extract_token(stdout)
    if not token:
        msg = f"Could not extract token from server response:\n{stdout}"
        raise BootstrapError(msg)
    return token


def extract_token(output: str) -> str | None:
    """
    Extract JWT token from command output.

    Args:
        output: Command output containing the token

    Returns:
        The JWT token or None if not found
    """
    return extract_jwt(output)


def get_magic_link_via_ssh(ssh_target: str, username: str = "admin") -> str:
    """
    Get a magic link via SSH for passwordless web login.

    This calls auth:magic-link on the server which generates a short-lived,
    single-use token that can be used to log into the web dashboard.

    Args:
        ssh_target: SSH target (user@host)
        username: Username to generate the magic link for (default: admin)

    Returns:
        Either a bare token, or a full URL when the server has a public admin
        domain configured (it knows its own scheme/host then; the CLI does not).
        The caller decides how to turn a bare token into a URL.

    Raises:
        BootstrapError: If the command fails
    """
    hop3_cmd = f"{HOP_SERVER_PATH} auth:magic-link {shlex.quote(username)}"
    stdout = _run_hop3_server(
        ssh_target, hop3_cmd, f"generate a dashboard link for {username!r}"
    )

    # The token is returned directly (just the JWT, no extra formatting).
    token = stdout.strip()
    if not token:
        msg = "Server returned empty response for magic link"
        raise BootstrapError(msg)

    return token


def _host_from_ssh_target(ssh_target: str) -> str:
    """Extract the bare host from an SSH target (user@host[:port] -> host)."""
    host = ssh_target.split("@")[1] if "@" in ssh_target else ssh_target
    return host.split(":")[0]  # strip any SSH port


def infer_server_url(ssh_target: str) -> str:
    """
    Infer HTTPS URL from SSH target.

    Args:
        ssh_target: SSH target (user@host or host)

    Returns:
        HTTPS URL for the server
    """
    return f"https://{_host_from_ssh_target(ssh_target)}"


def web_base_url(server_url: str | None, ssh_target: str) -> str:
    """
    Base URL for the web dashboard, to turn a bare magic-link token into a full
    URL when the server didn't return one itself.

    Prefer the scheme + host[:port] of the HTTP(S) server URL we already use to
    reach this host: that is where the dashboard is actually served (behind
    nginx/TLS for a real domain). Otherwise infer from the SSH host —
    ``https://<host>`` for a real host (a production Hop3 is TLS-fronted on 443),
    and ``http://<host>:8000`` only for a local dev server. The old blanket
    ``http://<host>:8000`` sent the magic token in cleartext to the wrong port on
    a TLS-fronted server.
    """
    host = _host_from_ssh_target(ssh_target)
    if server_url:
        parsed = urlparse(server_url)
        if parsed.scheme in {"http", "https"} and parsed.hostname == host:
            return f"{parsed.scheme}://{parsed.netloc}"  # keeps an explicit port
    if host in {"localhost", "127.0.0.1", "::1"}:
        return f"http://{host}:{DEFAULT_WEB_PORT}"
    return f"https://{host}"
