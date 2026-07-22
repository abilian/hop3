# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Reproducibility gate: rebuild each nix-gen app and check the output is stable.

The hermetic templates promise that the same source builds bit-for-bit the same
output. That promise is worth nothing unless something checks it, so this drives
``nix build`` followed by ``nix build --rebuild`` (which rebuilds and compares
against the first result) and reports any app whose output changed.

A failure is classified, not just recorded, because the dispositions are
different work. A *stale hash* is mechanical — re-derive it with
``hop3-tools nix vendor-hash`` — and is the ordinary outcome of moving the
nixpkgs pin. An *eval error* means an attribute was renamed or removed upstream
and a human has to decide. Genuine *non-determinism* is the defect this gate
exists to catch. Reporting all three as "not reproducible" hides which one you
are looking at, and on a pin bump nearly all of them are the harmless kind.

The parsing and the pass/fail decision are pure functions; the ``nix`` and SSH
calls live in the CLI, so the reporting logic is testable without a build.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum


class Outcome(StrEnum):
    """What a rebuild attempt actually established."""

    REPRODUCIBLE = "reproducible"
    NOT_DETERMINISTIC = "not deterministic"
    STALE_HASH = "stale hash"
    EVAL_ERROR = "eval error"
    BUILD_FAILED = "build failed"


# Ordered: a fixed-output hash mismatch names a *pinned* hash that no longer
# matches, which is not the same event as two builds of one derivation
# disagreeing. Checking it first keeps a pin bump from being reported as a
# determinism defect.
_PATTERNS: tuple[tuple[Outcome, re.Pattern[str]], ...] = (
    (Outcome.STALE_HASH, re.compile(r"hash mismatch in fixed-output derivation")),
    (
        Outcome.NOT_DETERMINISTIC,
        re.compile(r"output '.*' differs|derivation '.*' may not be deterministic"),
    ),
    (
        Outcome.EVAL_ERROR,
        re.compile(
            r"attribute '.*' missing|undefined variable|has been removed|"
            r"is not available on|error: evaluation aborted"
        ),
    ),
)

# What to do about each failure, so the report is actionable rather than a verdict.
REMEDY: dict[Outcome, str] = {
    Outcome.STALE_HASH: "re-derive with `hop3-tools nix vendor-hash <app-dir> --ssh <host>`",
    Outcome.NOT_DETERMINISTIC: "a real reproducibility defect — find the varying input",
    Outcome.EVAL_ERROR: "an attribute moved or vanished upstream — needs a decision",
    Outcome.BUILD_FAILED: "read the build log",
}


@dataclass(frozen=True, slots=True)
class ReproResult:
    app: str
    outcome: Outcome
    detail: str

    @property
    def reproducible(self) -> bool:
        return self.outcome is Outcome.REPRODUCIBLE


def classify(output: str) -> Outcome:
    """Which kind of failure a non-zero Nix build reported."""
    for outcome, pattern in _PATTERNS:
        if pattern.search(output):
            return outcome
    return Outcome.BUILD_FAILED


def interpret_rebuild(app: str, returncode: int, output: str) -> ReproResult:
    """Turn a ``nix build --rebuild`` outcome into a verdict.

    A zero exit means the rebuild matched the first build. Any non-zero exit is
    classified: none of them may be read as "reproducible".
    """
    if returncode == 0:
        return ReproResult(app, Outcome.REPRODUCIBLE, "rebuild matches")
    outcome = classify(output)
    if outcome is Outcome.BUILD_FAILED:
        tail = output.strip().splitlines()[-1:] or ["(no output)"]
        return ReproResult(app, outcome, f"build failed: {tail[0][:160]}")
    return ReproResult(app, outcome, str(outcome))


def summarize(results: list[ReproResult]) -> tuple[bool, str]:
    """Overall pass/fail and a summary grouped by outcome.

    Empty input is a failure — a gate that checked nothing must not report
    success.
    """
    if not results:
        return False, "no apps checked"
    bad = [r for r in results if not r.reproducible]
    if not bad:
        return True, f"all {len(results)} reproducible"

    counts = Counter(r.outcome for r in bad)
    lines = [f"{len(bad)} of {len(results)} not reproducible:"]
    for outcome, count in sorted(counts.items()):
        apps = ", ".join(r.app for r in bad if r.outcome is outcome)
        lines.append(f"  {count} {outcome} — {REMEDY[outcome]}")
        lines.append(f"    {apps}")
    return False, "\n".join(lines)
