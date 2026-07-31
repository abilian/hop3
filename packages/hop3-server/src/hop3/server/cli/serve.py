# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

import os

import granian
from granian.constants import Interfaces
from granian.log import LogLevels

# from hop3.config import MODE
from hop3.lib.registry import register
from hop3.server.security.rate_limit import LIMITER_STATE_IS_SHARED

from ._base import Command

MODE = os.environ.get("HOP3_MODE", "production")
HOST = os.environ.get("HOP3_HOST", "0.0.0.0")

# Number of worker processes.
#
# Pinned to 1: the auth rate limiter keeps its sliding window in process
# memory, so N workers would mean N independent limiters and an effective
# login limit of N x the configured 5/min -- silently, with the server still
# reporting 5/min. Raising this requires shared limiter state first; see
# `check_worker_count` below, which refuses the unsafe pairing rather than
# trusting a comment to be read.
WORKERS = 1

if MODE == "development":
    DEBUG = True
    LOG_LEVEL = LogLevels.debug
else:
    DEBUG = False
    LOG_LEVEL = LogLevels.info


def check_worker_count(workers: int, *, limiter_is_shared: bool) -> None:
    """
    Refuse to start multi-worker while rate-limiter state is per-process.

    Args:
        workers: Number of worker processes about to be started.
        limiter_is_shared: Whether limiter state is shared across processes.

    Raises:
        RuntimeError: if more than one worker would run against per-process
            limiter state.
    """
    if workers > 1 and not limiter_is_shared:
        msg = (
            f"Hop3 can't start with {workers} workers: the auth rate limiter "
            f"keeps its state in process memory, so each worker would enforce "
            f"its own 5/min budget and the real limit would be {workers}x that "
            f"— without saying so. Back the limiter with shared storage (Redis) "
            f"and set LIMITER_STATE_IS_SHARED, or run a single worker."
        )
        raise RuntimeError(msg)


@register
class Serve(Command):
    """Launch the server."""

    name = "serve"

    def run(self) -> None:
        reload = DEBUG
        check_worker_count(WORKERS, limiter_is_shared=LIMITER_STATE_IS_SHARED)
        granian.Granian(
            target="hop3.server.asgi:create_app",
            factory=True,
            address=HOST,
            workers=WORKERS,
            # port=port,
            interface=Interfaces.ASGI,
            log_dictconfig={"root": {"level": "DEBUG"}} if not DEBUG else {},
            log_level=LOG_LEVEL,
            log_access=True,
            # loop=Loops.uvloop,
            reload=reload,
        ).serve()
