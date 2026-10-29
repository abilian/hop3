# Copyright (c) 2023-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Safety interlock for the ``HOP3_UNSAFE`` test-mode auth bypass.

``HOP3_UNSAFE=true`` disables all authentication: the RPC controller
short-circuits auth checks (``server/controllers/rpc.py:409-411``), the
web auth guard returns without checking the session
(``server/guards.py:44-46``), and the root controller treats every
request as authenticated (``server/controllers/root.py:35-36``). That is
correct for integration tests and developer loopback runs; it is a total
compromise in production.

This module enforces two interlocks called once at server startup:

1. **ACK requirement** — setting ``HOP3_UNSAFE=true`` requires a sibling
   env var ``HOP3_UNSAFE_ACK=yes-I-understand``. The server refuses to
   start otherwise. Prevents accidental activation via a stray env file
   or systemd drop-in.
2. **Production override** — if ``MODE`` is ``production`` (the default
   per ``config.HopConfig.MODE``), ``HOP3_UNSAFE`` is forced to ``False``
   regardless of what the operator asked for, and the event is logged at
   CRITICAL. The server still starts, but with auth enabled.

The gate reads the three settings through the live config, as the auth
guards do: the environment first, then ``hop3-server.toml``. Reading only
``os.environ`` let ``HOP3_UNSAFE = true`` in the file disable authentication
with no acknowledgement and no production override. The environment outranks
the file, so forcing ``os.environ["HOP3_UNSAFE"]`` is what reaches the guards.
Never pin the value on the ``hop3.config`` module: a module attribute shadows
the live setting.
"""

from __future__ import annotations

import logging
import os

from hop3 import config as c

__all__ = [
    "UnsafeModeError",
    "enforce_unsafe_mode_policy",
]

logger = logging.getLogger(__name__)

ACK_VALUE = "yes-I-understand"
_PRODUCTION_MODES = frozenset({"production", "prod"})


class UnsafeModeError(RuntimeError):
    """Raised when ``HOP3_UNSAFE`` is set without the required ACK flag."""


def enforce_unsafe_mode_policy() -> None:
    """
    Apply the ``HOP3_UNSAFE`` safety interlocks.

    Call exactly once at server startup (``asgi.on_startup``) and before
    any code path that consults ``config.HOP3_UNSAFE``.

    Raises:
        UnsafeModeError: if ``HOP3_UNSAFE`` is requested without a correct
            ``HOP3_UNSAFE_ACK`` value.
    """
    if not c.HOP3_UNSAFE:
        return

    if c.HOP3_UNSAFE_ACK != ACK_VALUE:
        msg = (
            "HOP3_UNSAFE is enabled but HOP3_UNSAFE_ACK is not set to "
            f"'{ACK_VALUE}'. This is a safety interlock to prevent "
            "accidental activation of the test-mode auth bypass. Set "
            f"HOP3_UNSAFE_ACK='{ACK_VALUE}' to proceed, or unset "
            "HOP3_UNSAFE."
        )
        raise UnsafeModeError(msg)

    mode = c.MODE.strip().lower()
    if mode in _PRODUCTION_MODES:
        logger.critical(
            "SECURITY: HOP3_UNSAFE=true with MODE=%s. Forcing "
            "HOP3_UNSAFE=false; the auth bypass will have no effect. "
            "Check your environment — this combination is never correct "
            "in production.",
            mode,
        )
        os.environ["HOP3_UNSAFE"] = "false"
