# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Resource-limit resolution + mapping (ADR 046 §3 / P2.2) — functional core.

Pure transforms, no I/O: resolve a declared ``[limits]`` against the operator's
server-wide defaults and ceilings, and map the result to the cgroup-native form
hop3-rootd's ``cgroup.set_limits`` expects. The imperative shell (the deployer)
applies the result; the Docker builder reuses the resolved hop3.toml-form values
for its compose mapping, so defaults/ceilings apply uniformly across builders.

Limit forms:
  - ``memory``: a string like ``"512M"`` / ``"1G"`` (or bare bytes), per schema.
  - ``cpu``: fractional cores (e.g. ``1.5``).
  - ``processes``: an integer pids cap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Final

# Dimensions, in a stable order for deterministic messages/output.
_DIMS: Final[tuple[str, ...]] = ("memory", "cpu", "processes")

_MEMORY_RE: Final[re.Pattern[str]] = re.compile(r"^(\d+)([KMG]?)$", re.IGNORECASE)
_MEMORY_MULT: Final[dict[str, int]] = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3}

# cgroup v2 cpu.max period (microseconds); quota = cores * period.
_CPU_PERIOD_US: Final[int] = 100_000


class LimitsError(Exception):
    """
    A declared/defaulted limit is invalid or exceeds the server ceiling.

    Raised by the functional core; the deployer turns it into a loud deploy
    abort (a declared cap that can't be honored must never be silently dropped
    or clamped).
    """


@dataclass(frozen=True, slots=True)
class ResolvedLimits:
    """The effective caps after applying defaults + ceilings (hop3.toml-form)."""

    memory: str | None = None
    cpu: float | None = None
    processes: int | None = None

    def is_empty(self) -> bool:
        return self.memory is None and self.cpu is None and self.processes is None

    def as_dict(self) -> dict[str, Any]:
        """hop3.toml-form dict of the set dimensions (for the Docker mapping)."""
        out: dict[str, Any] = {}
        if self.memory is not None:
            out["memory"] = self.memory
        if self.cpu is not None:
            out["cpu"] = self.cpu
        if self.processes is not None:
            out["processes"] = self.processes
        return out


def parse_memory_to_bytes(value: str) -> int:
    """Parse a memory string (``"512M"``, ``"1G"``, bare bytes) to bytes."""
    m = _MEMORY_RE.match(value.strip())
    if not m:
        msg = f"invalid memory value {value!r}; expected e.g. '512M' or '1G'"
        raise LimitsError(msg)
    return int(m.group(1)) * _MEMORY_MULT[m.group(2).upper()]


def cpu_to_cgroup_max(cpu: float) -> str:
    """Map fractional cores to a cgroup v2 ``cpu.max`` ``"<quota> <period>"``."""
    quota = round(cpu * _CPU_PERIOD_US)
    return f"{quota} {_CPU_PERIOD_US}"


def resolve_limits(
    declared: dict[str, Any],
    defaults: dict[str, Any],
    ceilings: dict[str, Any],
) -> ResolvedLimits:
    """
    Resolve effective caps: declared wins, else the server default; abort if
    over the ceiling.

    Per-dimension and independent: an app may declare only ``memory`` and take
    the server default for ``cpu``. A value over its ceiling **aborts** (never
    silently clamps down — giving an app less than it asked for is the same
    class of lie as not enforcing). Both declared-over-ceiling and a
    misconfigured default-over-ceiling raise ``LimitsError``.
    """
    resolved: dict[str, Any] = {}
    for dim in _DIMS:
        if declared.get(dim) is not None:
            value, source = declared[dim], "declared"
        elif defaults.get(dim) is not None:
            value, source = defaults[dim], "server default"
        else:
            continue

        ceiling = ceilings.get(dim)
        if ceiling is not None and _exceeds(dim, value, ceiling):
            msg = (
                f"[limits].{dim} {value!r} ({source}) exceeds the server "
                f"ceiling of {ceiling!r}; lower it or ask the operator to raise "
                f"the ceiling."
            )
            raise LimitsError(msg)
        resolved[dim] = value

    return ResolvedLimits(
        memory=resolved.get("memory"),
        cpu=resolved.get("cpu"),
        processes=resolved.get("processes"),
    )


def to_cgroup_args(resolved: ResolvedLimits) -> dict[str, Any]:
    """Map resolved caps to ``cgroup.set_limits`` args (memory_max/cpu_max/pids_max)."""
    args: dict[str, Any] = {}
    if resolved.memory is not None:
        args["memory_max"] = parse_memory_to_bytes(str(resolved.memory))
    if resolved.cpu is not None:
        args["cpu_max"] = cpu_to_cgroup_max(float(resolved.cpu))
    if resolved.processes is not None:
        args["pids_max"] = int(resolved.processes)
    return args


def _exceeds(dim: str, value: float | str, ceiling: float | str) -> bool:
    """True if ``value`` exceeds ``ceiling`` for the given dimension."""
    if dim == "memory":
        return parse_memory_to_bytes(str(value)) > parse_memory_to_bytes(str(ceiling))
    return float(value) > float(ceiling)
