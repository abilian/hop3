# Copyright (c) 2023-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Out-of-line contracts for ``hop3.core.identifiers`` — proven, not promised.

Each ``@ensures`` is a statically PROVEN postcondition of the real validator
body (adjudicated by mcpython against the source; the production module keeps
zero mcpython dependency). All three are IDENTITY contracts: a validator
returns its input unchanged, never a normalized or substituted value — so a
caller that validates a name and then builds a path from the ORIGINAL string
is provably using the validated value.

Adjudicated by ``proofs/test_identifiers_contracts.py``, or by hand:

    mcpython check packages/hop3-server/src/hop3/core/identifiers.py \\
        packages/hop3-server/proofs/identifiers_contracts.py \\
        --lib packages/hop3-server/src
"""

from mcpython.harness import ensures

from hop3.core.identifiers import (
    validate_app_name,
    validate_env_var_key,
    validate_hostname,
    validate_hostname_list,
    validate_service_name,
)


@ensures(lambda name, result: result == name)
def validate_app_name(name): ...


# Identity holds on BOTH arms: the "_" nginx catch-all sentinel returns the
# very string it tested, and the RFC-1123 arm returns the fullmatch'd input.
# A refactor that starts normalising (lowercasing, stripping a trailing dot)
# flips this proof and fails the drift test.
@ensures(lambda host, result: result == host)
def validate_hostname(host): ...


@ensures(lambda name, result: result == name)
def validate_service_name(name): ...


@ensures(lambda key, result: result == key)
def validate_env_var_key(key): ...


# The parsed list is never empty: every accepted input yields at least one
# validated hostname (the empty case raises). Proven through the whole body
# — replace/split, the filtered comprehension, the per-element substitution
# of validate_hostname's own proven contract, and the emptiness guard.
@ensures(lambda value, result: len(result) >= 1)
def validate_hostname_list(value): ...
