# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""hop3-rootd — privileged-operations agent for Hop3.

Runs as root. Exposes a narrow set of typed-intent operations
(firewall.*, nginx.*, daemon.*) to hop3-server over a Unix socket.

See notes/adrs/041-privileged-operations-agent.md for the design.
"""

from __future__ import annotations

__version__ = "0.4.0"

# Wire-protocol version. Bump on incompatible protocol changes.
PROTOCOL_VERSION = 1
