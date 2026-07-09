# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""hop3-rootd — privileged-operations agent for Hop3.

Runs as root. Exposes a narrow set of typed-intent operations to
hop3-server over a Unix socket: firewall.* and nginx.* and daemon.*
(baseline, ADR 041 §2), cgroup.* and mount.* (ADR 041 §18 / ADR 046),
and proxy.* (ADR 041 §19 — addon-exposure forwarders, ADR 040).

See notes/adrs/041-privileged-operations-agent.md for the design.
"""

from __future__ import annotations

from importlib.metadata import version

# Single-sourced from package metadata so it can never drift from pyproject (it
# once hardcoded a stale "0.4.0"). daemon.py re-exports this and reports it in
# the rootd handshake — ADR 041 version lockstep.
__version__ = version("hop3-rootd")

# Wire-protocol version. Bump on incompatible protocol changes.
PROTOCOL_VERSION = 1
