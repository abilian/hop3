# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
In-memory rate limiter for auth endpoints.

Simple sliding-window counter keyed by client IP. Suitable for a
single-server deployment. For multi-server, replace with a Redis-backed
implementation.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

__all__ = ["LIMITER_STATE_IS_SHARED", "RateLimitError", "RateLimiter"]

# Whether limiter state is shared across processes.
#
# False means each worker process keeps its own sliding window, so N workers
# multiply the effective limit by N. `server/cli/serve.py` reads this to refuse
# a multi-worker start: a rate limit that silently permits 5xN attempts while
# reporting 5 is the platform lying about its own posture.
#
# Flip to True in the same change that backs the limiter with shared storage
# (Redis or equivalent) -- that is what lifts the single-worker restriction.
LIMITER_STATE_IS_SHARED = False


class RateLimitError(Exception):
    """Raised when an IP exceeds the configured rate limit."""

    def __init__(self, ip: str, retry_after: float) -> None:
        super().__init__(f"Rate limit exceeded for {ip}")
        self.ip = ip
        self.retry_after = retry_after


@dataclass
class RateLimiter:
    """
    Sliding-window rate limiter.

    Tracks request timestamps per key (typically client IP). When the
    number of requests in the window exceeds the limit, raises
    RateLimitError.

    Example:
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        try:
            limiter.check("192.0.2.1")
        except RateLimitError as e:
            return error(429, retry_after=e.retry_after)
    """

    max_requests: int = 5
    window_seconds: float = 60.0
    _buckets: dict[str, deque[float]] = field(
        default_factory=lambda: defaultdict(deque)
    )
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def check(self, key: str) -> None:
        """
        Record a request and raise if the rate limit is exceeded.

        Args:
            key: Identifier (typically client IP)

        Raises:
            RateLimitError: If the key has made too many requests
        """
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            bucket = self._buckets[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()

            if len(bucket) >= self.max_requests:
                # Time until the oldest request falls out of the window
                retry_after = bucket[0] + self.window_seconds - now
                raise RateLimitError(key, max(retry_after, 0.0))

            bucket.append(now)

    def reset(self, key: str | None = None) -> None:
        """
        Reset rate limit state.

        Args:
            key: If provided, reset only this key. Otherwise, reset all.
        """
        with self._lock:
            if key is None:
                self._buckets.clear()
            else:
                self._buckets.pop(key, None)
