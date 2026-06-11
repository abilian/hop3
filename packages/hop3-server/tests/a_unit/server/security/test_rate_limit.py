# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the in-memory rate limiter."""

from __future__ import annotations

import time

import pytest

from hop3.server.security.rate_limit import RateLimiter, RateLimitError


def test_allows_requests_under_limit():
    limiter = RateLimiter(max_requests=3, window_seconds=60.0)
    for _ in range(3):
        limiter.check("192.0.2.1")  # Should not raise


def test_blocks_request_over_limit():
    limiter = RateLimiter(max_requests=3, window_seconds=60.0)
    for _ in range(3):
        limiter.check("192.0.2.1")
    with pytest.raises(RateLimitError) as exc_info:
        limiter.check("192.0.2.1")
    assert exc_info.value.ip == "192.0.2.1"
    assert exc_info.value.retry_after >= 0


def test_independent_buckets_per_key():
    limiter = RateLimiter(max_requests=2, window_seconds=60.0)
    limiter.check("a")
    limiter.check("a")
    limiter.check("b")  # Different key, not affected
    limiter.check("b")
    with pytest.raises(RateLimitError):
        limiter.check("a")
    with pytest.raises(RateLimitError):
        limiter.check("b")


def test_window_slides_over_time():
    limiter = RateLimiter(max_requests=2, window_seconds=0.1)
    limiter.check("x")
    limiter.check("x")
    with pytest.raises(RateLimitError):
        limiter.check("x")
    time.sleep(0.15)  # Wait for window to slide
    limiter.check("x")  # Should not raise


def test_reset_clears_specific_key():
    limiter = RateLimiter(max_requests=1, window_seconds=60.0)
    limiter.check("a")
    limiter.check("b")
    limiter.reset("a")
    limiter.check("a")  # Should not raise (reset)
    with pytest.raises(RateLimitError):
        limiter.check("b")  # Still blocked


def test_reset_all_clears_everything():
    limiter = RateLimiter(max_requests=1, window_seconds=60.0)
    limiter.check("a")
    limiter.check("b")
    limiter.reset()
    limiter.check("a")
    limiter.check("b")


def test_retry_after_is_positive():
    limiter = RateLimiter(max_requests=1, window_seconds=10.0)
    limiter.check("x")
    with pytest.raises(RateLimitError) as exc_info:
        limiter.check("x")
    # Should be close to the window size on first overflow
    assert 9.0 < exc_info.value.retry_after <= 10.0
