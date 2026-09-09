# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Minting a fresh token over SSH, without asking the operator.

One implementation, called from both places that need it: the pre-flight check
in ``main`` and the 401 retry in the RPC client. They had a copy each, and each
gated on the *connection* being ``ssh://`` — which tied unattended renewal to
routing every command through a root shell. The gate is now the context's
bootstrap route, so an HTTPS context renews just as quietly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3_cli.exceptions import AuthenticationError

if TYPE_CHECKING:
    from hop3_cli.config import Config


def can_auto_authenticate(config: Config) -> bool:
    """Whether this connection knows an SSH route to mint a token through."""
    return config.get_bootstrap_target() is not None


def auto_authenticate(config: Config) -> str:
    """
    Mint a token over the bootstrap route and store it. Returns the target used.

    Raises ``AuthenticationError`` when there is no route, or the remote call
    fails — the caller decides whether that is fatal.
    """
    from hop3_cli.commands.local.ssh_ops import (  # ruff:ignore[import-outside-top-level]
        BootstrapError,
        get_ssh_token,
    )

    ssh_target = config.get_bootstrap_target()
    if not ssh_target:
        msg = (
            "This server has no SSH bootstrap route, so a token cannot be "
            "renewed automatically. Run `hop3 login <user>@<host>`."
        )
        raise AuthenticationError(msg)

    try:
        token = get_ssh_token(ssh_target)
    except BootstrapError as e:
        msg = f"SSH authentication to {ssh_target} failed: {e}"
        raise AuthenticationError(msg) from e

    config.update_context_token(token)
    return ssh_target
