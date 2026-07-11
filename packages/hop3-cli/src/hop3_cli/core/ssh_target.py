# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Validation for SSH targets handed to the system ``ssh`` binary.

Both the RPC tunnel (``core.ssh_tunnel``) and the remote-exec helpers
(``commands.local.ssh_ops``) assemble a ``user@host`` and pass it to ``ssh`` as
a positional argument. A value beginning with ``-`` would be parsed by ssh as
an *option* (e.g. ``-oProxyCommand=...`` → arbitrary command execution, audit
M1). This module is the single source of truth for rejecting such targets, so
the guard can't drift between the two call sites.
"""

from __future__ import annotations

import re

# A well-formed ssh target: ``[user@]host[:port]`` over a conservative charset.
# The leading character must NOT be ``-`` (that is the whole point). We always
# construct targets as ``user@host``, so this rejects only malformed/injected
# input, never a legitimate target. Anchored with ``\A``/``\Z`` (not ``$``,
# which in Python also matches just before a trailing newline).
_SSH_TARGET_RE = re.compile(r"\A[A-Za-z0-9_.][A-Za-z0-9_.@:+-]*\Z")


def is_safe_ssh_target(target: str) -> bool:
    """Whether ``target`` is a plain ``[user@]host[:port]`` safe to pass to ssh.

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
