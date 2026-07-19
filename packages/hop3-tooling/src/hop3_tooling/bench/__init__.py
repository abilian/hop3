# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""hop3-bench — the paper's benchmark harness (see notes/reports/paper-completion-plan.md §3).

Read-only, fail-loud measurement probes for a Hop3 target. The probes are the
measurement layer the paper's §6.4 protocol is built on; they are deliberately
separate from the pass/fail test runners (different lifecycle, different schema).
"""

from __future__ import annotations

from hop3_tooling.bench.probes import (
    BenchError,
    ClosureInfo,
    ControlPlaneMemory,
    control_plane_memory,
    docker_image_size,
    nix_closure,
    parse_closure,
    parse_docker_size,
    parse_pss_kb,
    union_closure,
)

__all__ = [
    "BenchError",
    "ClosureInfo",
    "ControlPlaneMemory",
    "control_plane_memory",
    "docker_image_size",
    "nix_closure",
    "parse_closure",
    "parse_docker_size",
    "parse_pss_kb",
    "union_closure",
]
