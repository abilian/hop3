# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Reproducibility gate: rebuild each nix-gen app and check the output is stable.

The hermetic templates promise that the same source builds bit-for-bit the same
output. That promise is worth nothing unless something checks it, so this drives
``nix build`` followed by ``nix build --rebuild`` (which rebuilds and compares
against the first result) and reports any app whose output changed.

The parsing and the pass/fail decision are pure functions; the ``nix`` and SSH
calls live in the CLI, so the reporting logic is testable without a build.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# `nix build --rebuild` prints this when a second build differs from the first.
_HASH_MISMATCH = re.compile(
    r"hash mismatch in fixed-output|output '.*' differs|"
    r"derivation '.*' may not be deterministic"
)


@dataclass(frozen=True, slots=True)
class ReproResult:
    app: str
    reproducible: bool
    detail: str


def interpret_rebuild(app: str, returncode: int, output: str) -> ReproResult:
    """Turn a ``nix build --rebuild`` outcome into a verdict.

    A zero exit means the rebuild matched the first build. A non-zero exit that
    mentions a determinism mismatch is a *result* (the app is not reproducible),
    not a tooling error; any other non-zero exit is an error we must not read as
    "reproducible".
    """
    if returncode == 0:
        return ReproResult(app, reproducible=True, detail="rebuild matches")
    if _HASH_MISMATCH.search(output):
        return ReproResult(
            app, reproducible=False, detail="output is not deterministic"
        )
    # A build failure for some other reason — surface it, don't count it as a pass.
    tail = output.strip().splitlines()[-1:] or ["(no output)"]
    return ReproResult(app, reproducible=False, detail=f"build failed: {tail[0][:160]}")


def summarize(results: list[ReproResult]) -> tuple[bool, str]:
    """Overall pass/fail and a one-line summary. Empty input is a failure —
    a gate that checked nothing must not report success."""
    if not results:
        return False, "no apps checked"
    bad = [r for r in results if not r.reproducible]
    if bad:
        lines = "; ".join(f"{r.app} ({r.detail})" for r in bad)
        return False, f"{len(bad)} of {len(results)} not reproducible: {lines}"
    return True, f"all {len(results)} reproducible"
