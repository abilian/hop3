# Copyright (c) 2023-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Out-of-line contracts for ``hop3_rootd.validation`` — proven, not promised.

Each ``@ensures`` below is a statically PROVEN postcondition of the real
validator body: forall adjudicates this spec against the source and the
claim holds for every input the type admits, or the proof fails. The
production module keeps zero forall dependency — the contracts live here,
out of line, exactly so the daemon's ADR 041 "no external dependencies" rule
is untouched.

What each contract buys:

- ``validate_port``:       the returned port is always in [1, 65535].
- ``validate_memory_max``: the returned byte count is always >= 1.
- ``validate_pids_max``:   the returned limit is always >= 1.
- ``validate_app_name``, ``validate_cpu_max``, ``validate_protocol``:
  IDENTITY — the validator returns its input unchanged (never a normalized
  or substituted value), so callers may keep using the value they already
  hold. A refactor that starts transforming the value (a "parse, don't
  validate" change of semantics) flips the proof and fails the drift test.

Adjudicated by ``proofs/test_validation_contracts.py`` under pytest (when
forall is installed), or by hand:

    forall check packages/hop3-rootd/src/hop3_rootd/validation.py \\
        packages/hop3-rootd/proofs/validation_contracts.py \\
        --lib packages/hop3-rootd/src
"""

from forall.harness import ensures

from hop3_rootd.validation import (
    validate_app_name,
    validate_cpu_max,
    validate_memory_max,
    validate_pids_max,
    validate_port,
    validate_protocol,
)


@ensures(lambda value, result: 1 <= result <= 65535)
def validate_port(value): ...


@ensures(lambda value, result: result == value)
def validate_protocol(value): ...


@ensures(lambda value, result: result >= 1)
def validate_memory_max(value): ...


@ensures(lambda value, result: result >= 1)
def validate_pids_max(value): ...


@ensures(lambda value, result: result == value)
def validate_app_name(value): ...


@ensures(lambda value, result: result == value)
def validate_cpu_max(value): ...
