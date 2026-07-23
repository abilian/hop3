# Copyright (c) 2023-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Drift detection: every contract in ``identifiers_contracts.py`` must PROVE.

Re-adjudicates the out-of-line spec against the live source on every run; a
refactor that changes what a validator returns fails here, naming the broken
contract. Skips without mcpython (a dev tool).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("mcpython", reason="contract adjudication needs mcpython")

from mcpython.symbolic import Proven, _external_contracts, verify_file

_SRC = Path(__file__).resolve().parents[1] / "src"
_IDENTIFIERS = _SRC / "hop3" / "core" / "identifiers.py"
_SPEC = Path(__file__).with_name("identifiers_contracts.py")

_CONTRACTED = {
    "validate_app_name",
    "validate_service_name",
    "validate_env_var_key",
    "validate_hostname",
}


def test_every_identifier_contract_proves() -> None:
    external = _external_contracts((_IDENTIFIERS, _SPEC), (_SRC,))
    results = {
        r.function: r
        for r in verify_file(
            _IDENTIFIERS,
            roots=(_SRC,),
            external_contracts=external.get(_IDENTIFIERS.resolve()),
        )
    }
    broken = {
        name: getattr(results.get(name), "reason", "missing")
        for name in sorted(_CONTRACTED)
        if not (
            isinstance(results.get(name), Proven)
            and results[name].contract
        )
    }
    assert not broken, f"contracts no longer prove against the live source: {broken}"
