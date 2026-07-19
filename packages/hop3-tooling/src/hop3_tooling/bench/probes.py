# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Benchmark probes: pure parsers + fail-loud measurement functions.

Each probe takes a ``run(cmd) -> str`` callable (a local shell or an SSH shell)
and returns a frozen result. Probes **raise** on a missing tool, an empty
process set, or unparsable output — a swallowed probe is a fake data point, and
the platform's rule is that errors are never silent. Parsers are separated from
the runner so they can be unit-tested against captured output with no I/O.
"""

from __future__ import annotations

import json
import shlex
from collections.abc import Callable, Iterable
from dataclasses import dataclass

Runner = Callable[[str], str]


class BenchError(RuntimeError):
    """A probe could not produce a trustworthy measurement."""


# --- pure parsers (no I/O) --------------------------------------------------


def parse_pss_kb(smaps_rollup: str) -> int:
    """Sum the ``Pss:`` field (kB) from a ``/proc/<pid>/smaps_rollup`` dump."""
    total = 0
    seen = False
    for line in smaps_rollup.splitlines():
        if line.startswith("Pss:"):
            total += int(line.split()[1])
            seen = True
    if not seen:
        msg = "no Pss field in smaps_rollup — cannot measure PSS"
        raise BenchError(msg)
    return total


def parse_closure(path_info_json: str) -> ClosureInfo:
    """Parse ``nix path-info -r --json <path>`` into a closure summary.

    Handles both the object form (newer Nix, keyed by store path) and the list
    form (Nix 2.x). The closure size is the sum of every path's ``narSize``.
    """
    data = json.loads(path_info_json)
    records = list(data.values()) if isinstance(data, dict) else list(data)
    if not records:
        msg = "empty path-info output — nothing to measure"
        raise BenchError(msg)
    closure_bytes = sum(int(r.get("narSize") or 0) for r in records)
    if closure_bytes <= 0:
        msg = "path-info reported a zero-byte closure"
        raise BenchError(msg)
    return ClosureInfo(closure_bytes=closure_bytes, path_count=len(records))


def parse_docker_size(inspect_output: str) -> int:
    """Parse the bytes printed by ``docker image inspect --format '{{.Size}}'``."""
    text = inspect_output.strip()
    if not text.isdigit():
        msg = f"docker image size is not a number: {text!r}"
        raise BenchError(msg)
    return int(text)


# --- results ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ControlPlaneMemory:
    pids: tuple[int, ...]
    pss_kb: int
    rss_kb: int

    @property
    def pss_mb(self) -> float:
        return round(self.pss_kb / 1024, 1)

    @property
    def rss_mb(self) -> float:
        return round(self.rss_kb / 1024, 1)


@dataclass(frozen=True, slots=True)
class ClosureInfo:
    closure_bytes: int
    path_count: int

    @property
    def closure_mb(self) -> float:
        return round(self.closure_bytes / 1_000_000, 1)


# --- fail-loud probes (I/O via the runner) ----------------------------------


def control_plane_memory(
    run: Runner, pattern: str = "hop3-server serve"
) -> ControlPlaneMemory:
    """Measure the resident memory of the Hop3 control plane (PSS + RSS).

    The management set is every process whose argv matches ``pattern``
    (the ASGI master and its workers). Raises if nothing matches — an empty
    set would silently report zero.
    """
    pids = [int(p) for p in run(f"pgrep -f {shlex.quote(pattern)}").split()]
    if not pids:
        msg = f"no process matches {pattern!r}: control plane not running"
        raise BenchError(msg)
    pss = 0
    rss = 0
    for pid in pids:
        pss += parse_pss_kb(run(f"cat /proc/{pid}/smaps_rollup"))
        rss += _parse_vmrss_kb(run(f"grep VmRSS /proc/{pid}/status"))
    return ControlPlaneMemory(pids=tuple(pids), pss_kb=pss, rss_kb=rss)


def nix_closure(run: Runner, store_path: str) -> ClosureInfo:
    """Uncompressed runtime closure size + path count of a Nix store path."""
    out = run(f"nix path-info -r --json {shlex.quote(store_path)}")
    return parse_closure(out)


def union_closure(run: Runner, store_paths: Iterable[str]) -> ClosureInfo:
    """Deduplicated closure of several store paths (each shared path counted once)."""
    quoted = " ".join(shlex.quote(p) for p in store_paths)
    if not quoted:
        msg = "union_closure needs at least one store path"
        raise BenchError(msg)
    return parse_closure(run(f"nix path-info -r --json {quoted}"))


def docker_image_size(run: Runner, image: str) -> int:
    """Uncompressed size (bytes) of a pulled Docker image."""
    out = run(f"docker image inspect --format '{{{{.Size}}}}' {shlex.quote(image)}")
    return parse_docker_size(out)


def _parse_vmrss_kb(status_line: str) -> int:
    parts = status_line.split()
    if len(parts) < 2 or not parts[1].isdigit():
        msg = f"cannot parse VmRSS from {status_line!r}"
        raise BenchError(msg)
    return int(parts[1])
