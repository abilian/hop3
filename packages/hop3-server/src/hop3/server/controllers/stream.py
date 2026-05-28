# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""SSE streaming endpoint for deployment logs.

This controller provides a Server-Sent Events endpoint for streaming
deployment logs to CLI clients in real-time.

Usage:
    GET /api/stream/{stream_id}

    Returns an SSE stream with events:
    - event: log, data: {"msg": "...", "level": 0, "fg": "green"}
    - event: complete, data: {"success": true, "duration": 45.2}
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from litestar import Controller, get
from litestar.exceptions import NotFoundException
from litestar.response import Stream

from hop3.server.guards import auth_guard
from hop3.server.streaming import get_stream

if TYPE_CHECKING:
    from litestar.params import FromPath


class StreamController(Controller):
    """Controller for SSE log streaming.

    Provides endpoints for:
    - Streaming deployment logs via SSE
    - Checking stream status

    All endpoints require authentication. Without the guard any caller
    could guess a stream id and silently tail live deployment logs,
    which leak env vars and tokens.
    """

    path = "/api/stream"
    guards = [auth_guard]  # noqa: RUF012 - base class defines as instance var

    @get("/{stream_id:str}")
    async def stream_logs(self, stream_id: FromPath[str]) -> Stream:
        """Stream deployment logs via Server-Sent Events.

        Args:
            stream_id: Unique identifier for the deployment stream

        Returns:
            SSE stream of log events

        Raises:
            NotFoundException: If stream doesn't exist
        """
        stream = get_stream(stream_id)
        if not stream:
            msg = f"Stream '{stream_id}' not found"
            raise NotFoundException(msg)

        return Stream(
            stream.subscribe(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )

    @get("/{stream_id:str}/status")
    async def stream_status(self, stream_id: FromPath[str]) -> dict:
        """Get current status of a deployment stream.

        Args:
            stream_id: Unique identifier for the deployment stream

        Returns:
            Stream status including completion state, log count, etc.

        Raises:
            NotFoundException: If stream doesn't exist
        """
        stream = get_stream(stream_id)
        if not stream:
            msg = f"Stream '{stream_id}' not found"
            raise NotFoundException(msg)

        return stream.get_status()
