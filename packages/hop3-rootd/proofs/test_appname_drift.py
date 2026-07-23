# Copyright (c) 2023-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Server and rootd accept the SAME app names — semantic drift protection.

hop3 validates app names twice: hop3-server at the RPC boundary, hop3-rootd
again at the kernel boundary, because the daemon distrusts its caller. The
regexes are deliberately duplicated (ADR 041: no runtime deps on hop3-server),
and ``test_app_name_re_matches_hop3_server_upstream`` keeps the pattern
STRINGS in lockstep. That test is blind to one drift class we actually
shipped: identical patterns checked with different METHODS (``.match`` admits
one trailing newline that ``.fullmatch`` rejects — see the trailing-newline
section of test_validation.py). This file states the semantic fact instead:

    for every input, the server's gate accepts iff rootd's gate accepts.

It runs two ways. Under plain pytest (mcpython installed) each ``@proof``
below executes as a property test over a pool of boundary inputs — trailing
newlines, control characters, over-length strings — plus the pinned inputs
from the bug we already met. Under ``mcpython check`` the same harness is
PROVEN for every string, at every length:

    mcpython check packages/hop3-rootd/src packages/hop3-server/src \\
        packages/hop3-rootd/tests/a_unit/test_appname_drift.py

Without mcpython installed the module skips; the pattern-string parity test
keeps guarding, dependency-free.

HONESTY BOX: each wrapper below must mirror how its validator actually CALLS
the pattern (``fullmatch``, on both sides, since the 2026-07 fix). That
duplication is the residual gap this file cannot close about itself — the
same trap as the string test, one level up. If you change a validator's
method, change its wrapper here in the same commit.
"""

from __future__ import annotations

import pytest
from hop3_rootd.validation import ValidationError, validate_app_name as rootd_validate

from hop3.core.identifiers import (
    InvalidIdentifierError,
    validate_app_name as server_validate,
)

pytest.importorskip("mcpython", reason="drift proof needs mcpython (dev tool)")

from hop3_rootd.validation import APP_NAME_RE as ROOTD_APP_RE
from mcpython.harness import any_str, assume, proof
from mcpython.proptest import harness_tests

from hop3.core.identifiers import APP_NAME_RE as SERVER_APP_RE


def server_accepts(s: str) -> bool:
    """Mirrors ``hop3.core.identifiers._validate_identifier`` (fullmatch)."""
    return SERVER_APP_RE.fullmatch(s) is not None


def rootd_accepts(s: str) -> bool:
    """Mirrors ``hop3_rootd.validation.validate_app_name`` (fullmatch)."""
    return ROOTD_APP_RE.fullmatch(s) is not None


@proof
def server_and_rootd_accept_the_same_app_names() -> None:
    s = any_str()
    assume(len(s) <= 6)  # checked, not trusted: the engine re-proves without it
    assert server_accepts(s) == rootd_accepts(s)


# The pins replay the drift we shipped: '0-ah\n' is exactly the kind of input
# `.match` on the rootd side accepted while the server rejected it. With both
# gates on `fullmatch` the two sides agree (both reject); any regression to
# `.match` on either side fails these deterministically, before any proof runs.
test_appname_drift_properties = harness_tests(
    globals(),
    pins={
        "server_and_rootd_accept_the_same_app_names": [
            ("0-ah\n",),
            ("abc\n",),
            ("abc",),
            ("ab",),
        ],
    },
)


# --- The same statement, through the validators' REAL BODIES ---------------
# The wrappers above mirror each validator's method choice by hand (the
# honesty box). These observe the validators themselves: the raise IS the
# rejection, so a method drift in validation.py or identifiers.py breaks
# this with no edit here.


def server_validates(s: str) -> bool:
    try:
        server_validate(s)
    except InvalidIdentifierError:
        return False
    return True


def rootd_validates(s: str) -> bool:
    try:
        rootd_validate(s)
    except ValidationError:
        return False
    return True


@proof
def the_validators_themselves_accept_the_same_app_names() -> None:
    s = any_str()
    assume(len(s) <= 6)
    assert server_validates(s) == rootd_validates(s)


test_validator_body_drift = harness_tests(
    globals(),
    pins={
        "the_validators_themselves_accept_the_same_app_names": [
            ("0-ah\n",),
            ("abc\n",),
            ("abc",),
            ("ab",),
        ],
    },
)
