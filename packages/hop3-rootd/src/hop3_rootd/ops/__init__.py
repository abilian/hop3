# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Operation handlers exposed by hop3-rootd.

Importing this package triggers registration of all v1 ops via the
side-effects in each submodule. The dispatcher then consults the
registry in `_base.py` for op names it sees on the wire.
"""

from __future__ import annotations

# Side-effect imports: each module's @register decorators run on import.
from hop3_rootd.ops import (  # ruff:ignore[unused-import]
    cgroup,
    daemon,
    firewall,
    mount,
    nginx,
    postfix,
    proxy,
    service,
)
from hop3_rootd.ops._base import (
    OpContext,
    OpRegistration,
    StateConflictError,
    all_ops,
    get_handler,
    get_registration,
    register,
)

__all__ = [
    "OpContext",
    "OpRegistration",
    "StateConflictError",
    "all_ops",
    "get_handler",
    "get_registration",
    "register",
]
