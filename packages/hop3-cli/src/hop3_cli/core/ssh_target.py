# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Validation for SSH targets handed to the system ``ssh`` binary.

Both the RPC tunnel (``core.ssh_tunnel``) and the remote-exec helpers
(``commands.local.ssh_ops``) assemble a ``user@host`` and pass it to ``ssh`` as
a positional argument. A value beginning with ``-`` would be parsed by ssh as
an *option* (e.g. ``-oProxyCommand=...`` → arbitrary command execution, audit
M1). This module is the single source of truth for rejecting such targets, so
the guard can't drift between the two call sites.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from urllib.parse import urlparse

if TYPE_CHECKING:
    from hop3_cli.config import Config

#: What every ssh the CLI spawns carries: a bounded connect, keepalives so a
#: dropped link surfaces, and trust on first use for the host key (the tunnel
#: always accepted new keys; the bootstrap and the shell now do the same).
CONNECT_TIMEOUT_S: Final = 10
ALIVE_INTERVAL_S: Final = 15
DEFAULT_SSH_PORT: Final = 22

# A well-formed ssh target: ``[user@]host[:port]`` over a conservative charset.
# The leading character must NOT be ``-`` (that is the whole point). We always
# construct targets as ``user@host``, so this rejects only malformed/injected
# input, never a legitimate target. Anchored with ``\A``/``\Z`` (not ``$``,
# which in Python also matches just before a trailing newline).
_SSH_TARGET_RE = re.compile(r"\A[A-Za-z0-9_.][A-Za-z0-9_.@:+-]*\Z")


@dataclass(frozen=True, slots=True)
class SshSettings:
    """
    The CLI's ssh settings: ``ssh_key``, ``ssh_port``, ``ssh_options``.

    Read once from the config (``HOP3_SSH_KEY``, ``HOP3_SSH_PORT``,
    ``HOP3_SSH_OPTIONS`` override the file), then applied by ``ssh_base_argv``
    to every ssh the CLI spawns: the RPC tunnel, ``hop3 tunnel``,
    ``hop3 app shell`` and the ``hop3 login`` bootstrap.
    """

    key: str | None = None
    port: int = DEFAULT_SSH_PORT
    options: tuple[str, ...] = ()

    @classmethod
    def from_config(cls, config: Config) -> SshSettings:
        key = config.get("ssh_key", None)
        return cls(
            key=key if isinstance(key, str) and key else None,
            port=int(config.get("ssh_port", DEFAULT_SSH_PORT)),
            options=tuple(ssh_options_from(config.get("ssh_options", ""))),
        )


@dataclass(frozen=True, slots=True)
class SshEndpoint:
    """The ``ssh://`` server the CLI is pointed at, with the settings to reach it."""

    host: str
    user: str
    port: int
    settings: SshSettings

    @property
    def target(self) -> str:
        return f"{self.user}@{self.host}"


def ssh_base_argv(settings: SshSettings, *, port: int | None = None) -> list[str]:
    """
    ``ssh`` with the settings applied, for a caller to add its flags and target.

    ``port`` is the one the caller resolved (from an ``ssh://`` URL or a
    ``host:port`` target); it falls back to the settings' port, and ``-p`` is
    passed only when that differs from ssh's default.
    """
    argv = [
        "ssh",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", f"ConnectTimeout={CONNECT_TIMEOUT_S}",
        "-o", f"ServerAliveInterval={ALIVE_INTERVAL_S}",
    ]  # fmt: skip
    for option in settings.options:
        argv += ["-o", option]
    if settings.key:
        argv += ["-i", settings.key]
    effective_port = settings.port if port is None else port
    if effective_port != DEFAULT_SSH_PORT:
        argv += ["-p", str(effective_port)]
    return argv


def split_ssh_target(target: str) -> tuple[str, int | None]:
    """
    ``user@host[:port]`` as ``("user@host", port)``; ``port`` is None if absent.

    ``ssh`` takes the port as ``-p``, never in the target, so every caller that
    accepts the ``host:port`` spelling (the same one ``ssh://`` URLs use) splits
    it here.
    """
    user_host, sep, port = target.rpartition(":")
    if not sep:
        return target, None
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        msg = f"invalid SSH port in {target!r}: expected user@host[:port]"
        raise ValueError(msg)
    return user_host, int(port)


def ssh_options_from(value: object) -> list[str]:
    """
    The ``ssh -o`` values in the ``ssh_options`` setting (``HOP3_SSH_OPTIONS``).

    One string, whitespace-separated, shell-quoted where a value needs it:
    ``"ProxyJump=bastion UserKnownHostsFile=/tmp/kh"``. Every ssh the CLI
    spawns (the RPC tunnel, ``hop3 tunnel``, ``hop3 app shell``, the
    ``hop3 login`` bootstrap) passes each one as ``-o <value>``.
    """
    if not isinstance(value, str) or not value.strip():
        return []
    return shlex.split(value)


#: The URL schemes that mean "reach this server by opening an SSH tunnel".
#: ``ssh+http`` is the tunnel that speaks plain HTTP at the far end.
SSH_SCHEMES: tuple[str, ...] = ("ssh", "ssh+http")


def is_ssh_address(address: str | None) -> bool:
    """
    Whether ``address`` is reached over SSH — and so is its own bootstrap route.

    One statement of the rule. It was four: two ``startswith`` tuples in
    ``config``, one in ``main`` and a scheme set in the RPC client, which is
    three chances for them to drift apart on the day a scheme is added.
    """
    if not address:
        return False
    scheme, sep, _ = address.partition("://")
    return bool(sep) and scheme in SSH_SCHEMES


def ssh_target_from_address(address: str, default_user: str) -> str | None:
    """``ssh://[user@]host[:port]`` as the ``user@host[:port]`` ssh is given."""
    parsed = urlparse(address)
    if not parsed.hostname:
        return None
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.username or default_user}@{parsed.hostname}{port}"


def is_safe_ssh_target(target: str) -> bool:
    """
    Whether ``target`` is a plain ``[user@]host[:port]`` safe to pass to ssh.

    Rejects a leading ``-`` (ssh would read it as an option → ProxyCommand
    RCE), an empty or ``-``-leading host, and shell metacharacters.
    """
    host = target.rsplit("@", 1)[-1].split(":", 1)[0]
    return not (
        target.startswith("-")
        or not host
        or host.startswith("-")
        or not _SSH_TARGET_RE.match(target)
    )
