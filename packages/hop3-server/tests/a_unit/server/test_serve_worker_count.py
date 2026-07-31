# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The server may not run multi-worker while the rate limiter is per-process.

Each worker keeps its own sliding window, so N workers enforce N x the
configured login budget while the server still reports the configured one --
a silently weakened control, which is worse than a loudly absent one.

See notes/security/report-2026-07.md finding 5.
"""

from __future__ import annotations

import pytest

from hop3.server.cli.serve import WORKERS, check_worker_count
from hop3.server.security.rate_limit import LIMITER_STATE_IS_SHARED


def test_single_worker_is_allowed_with_in_memory_limiter() -> None:
    check_worker_count(1, limiter_is_shared=False)


@pytest.mark.parametrize("workers", [2, 4, 16])
def test_multi_worker_refused_with_in_memory_limiter(workers: int) -> None:
    with pytest.raises(RuntimeError, match="rate limiter"):
        check_worker_count(workers, limiter_is_shared=False)


@pytest.mark.parametrize("workers", [1, 2, 16])
def test_multi_worker_allowed_once_limiter_state_is_shared(workers: int) -> None:
    """Sharing limiter state is exactly what lifts the restriction."""
    check_worker_count(workers, limiter_is_shared=True)


def test_shipped_configuration_is_self_consistent() -> None:
    """
    The values the server actually starts with must satisfy the check.

    This is the test that fires if someone raises WORKERS without moving the
    limiter to shared storage -- the failure mode the guard exists for.
    """
    check_worker_count(WORKERS, limiter_is_shared=LIMITER_STATE_IS_SHARED)
