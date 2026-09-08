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

# A well-formed ssh target: ``[user@]host[:port]`` over a conservative charset.
# The leading character must NOT be ``-`` (that is the whole point). We always
# construct targets as ``user@host``, so this rejects only malformed/injected
# input, never a legitimate target. Anchored with ``\A``/``\Z`` (not ``$``,
# which in Python also matches just before a trailing newline).
_SSH_TARGET_RE = re.compile(r"\A[A-Za-z0-9_.][A-Za-z0-9_.@:+-]*\Z")


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
    ``login --ssh`` bootstrap) passes each one as ``-o <value>``.
    """
    if not isinstance(value, str) or not value.strip():
        return []
    return shlex.split(value)


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
