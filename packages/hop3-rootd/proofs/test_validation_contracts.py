# Copyright (c) 2023-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Drift detection: every contract in ``validation_contracts.py`` must PROVE.

This test re-adjudicates the out-of-line spec against the live validator
source on every run. A refactor that changes what a validator returns — the
class of change a pattern-string parity test is blind to — flips its proof
from Proven to Inconclusive and fails here, naming the contract that broke.
(We watched this fire for real: the 2026-07 "parse, don't validate" refactor
was contract-compatible, and these proofs held through it unchanged.)

Skips without forall (a dev tool); the runtime test suite keeps guarding
behavior, dependency-free.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("forall", reason="contract adjudication needs forall")

from forall.symbolic import Proven, _external_contracts, verify_file

_PKG = Path(__file__).resolve().parents[1]
_SRC = _PKG / "src"
_VALIDATION = _SRC / "hop3_rootd" / "validation.py"
_SPEC = Path(__file__).with_name("validation_contracts.py")

_CONTRACTED = {
    "validate_port",
    "validate_protocol",
    "validate_memory_max",
    "validate_pids_max",
    "validate_app_name",
    "validate_cpu_max",
}


def test_every_validation_contract_proves() -> None:
    external = _external_contracts((_VALIDATION, _SPEC), (_SRC,))
    results = {
        r.function: r
        for r in verify_file(
            _VALIDATION,
            roots=(_SRC,),
            external_contracts=external.get(_VALIDATION.resolve()),
        )
    }
    broken = {
        name: getattr(results.get(name), "reason", "missing")
        for name in sorted(_CONTRACTED)
        if not (
            isinstance(results.get(name), Proven)
            and results[name].contract  # proven AGAINST the contract, not merely safe
        )
    }
    assert not broken, f"contracts no longer prove against the live source: {broken}"
