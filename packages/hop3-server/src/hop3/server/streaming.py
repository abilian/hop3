# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Server-Sent Events streaming for deployment logs.

This module provides infrastructure for streaming deployment logs to CLI clients
in real-time via Server-Sent Events (SSE).

Usage:
    # Server-side: create a stream and route logs to it
    stream = create_stream("myapp")
    with stream_context(stream):
        do_deploy(app)  # All log() calls go to the stream
    stream.finish(success=True)

    # Client-side: connect to SSE endpoint
    GET /api/stream/{stream_id}
"""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# Stream registry
_streams: dict[str, DeploymentStream] = {}
STREAM_TTL_SECONDS = 3600  # 1 hour

# Thread-local storage for current stream context
# This ensures concurrent deployments don't interleave logs
_local = threading.local()


@dataclass
class LogEntry:
    """A single log entry."""

    msg: str
    level: int = 0
    fg: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "msg": self.msg,
            "level": self.level,
            "fg": self.fg,
            "timestamp": self.timestamp.isoformat(),
        }

    def to_sse(self) -> str:
        """Format as SSE event."""
        data = json.dumps(self.to_dict())
        return f"event: log\ndata: {data}\n\n"


@dataclass
class DeploymentStream:
    """Captures deployment logs and streams to connected clients.

    This class implements a pub/sub pattern where:
    - The deployment process writes logs via write()
    - Connected SSE clients subscribe via subscribe()
    - Logs are buffered so late-connecting clients can catch up
    """

    stream_id: str
    app_name: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    logs: list[LogEntry] = field(default_factory=list)
    subscribers: list[asyncio.Queue] = field(default_factory=list)
    complete: bool = False
    success: bool = False
    error_message: str = ""

    def write(self, msg: str, level: int = 0, fg: str = "") -> None:
        """Write a log entry and notify all subscribers.

        Args:
            msg: Log message
            level: Verbosity level (0=important, 1=normal, 2=verbose, 3=debug)
            fg: Color hint (green, red, blue, yellow, etc.)
        """
        entry = LogEntry(msg=msg, level=level, fg=fg)
        self.logs.append(entry)

        # Notify all subscribers
        for queue in self.subscribers:
            try:
                queue.put_nowait(("log", entry))
            except asyncio.QueueFull:
                pass  # Skip slow consumers

    def finish(self, success: bool, error_message: str = "") -> None:
        """Mark stream as complete.

        Args:
            success: Whether deployment succeeded
            error_message: Error message if failed
        """
        self.complete = True
        self.success = success
        self.error_message = error_message

        # Notify subscribers of completion
        for queue in self.subscribers:
            try:
                queue.put_nowait(("complete", None))
            except asyncio.QueueFull:
                pass

    async def subscribe(self) -> AsyncIterator[str]:
        """Subscribe to this stream and yield SSE-formatted events.

        Yields:
            SSE-formatted strings ready to send to client
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self.subscribers.append(queue)

        try:
            # First, send all existing logs (catch-up)
            for entry in self.logs:
                yield entry.to_sse()

            # If already complete, send completion event and return
            if self.complete:
                yield self._completion_event()
                return

            # Stream new logs as they arrive
            while True:
                try:
                    event_type, data = await asyncio.wait_for(queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    # Send keepalive comment to prevent connection timeout
                    yield ": keepalive\n\n"
                    continue

                if event_type == "complete":
                    yield self._completion_event()
                    return
                elif event_type == "log":
                    yield data.to_sse()

        finally:
            if queue in self.subscribers:
                self.subscribers.remove(queue)

    def _completion_event(self) -> str:
        """Generate SSE completion event."""
        duration = (datetime.now(UTC) - self.created_at).total_seconds()
        data = {
            "success": self.success,
            "error": self.error_message,
            "duration": duration,
            "log_count": len(self.logs),
        }
        return f"event: complete\ndata: {json.dumps(data)}\n\n"

    def get_status(self) -> dict[str, Any]:
        """Get current stream status."""
        return {
            "stream_id": self.stream_id,
            "app_name": self.app_name,
            "complete": self.complete,
            "success": self.success,
            "error_message": self.error_message,
            "log_count": len(self.logs),
            "subscriber_count": len(self.subscribers),
            "created_at": self.created_at.isoformat(),
            "duration": (datetime.now(UTC) - self.created_at).total_seconds(),
        }


def create_stream(app_name: str) -> DeploymentStream:
    """Create a new deployment stream.

    Args:
        app_name: Name of the app being deployed

    Returns:
        New DeploymentStream instance
    """
    # Clean up old streams first
    cleanup_old_streams()

    stream_id = str(uuid.uuid4())[:8]
    stream = DeploymentStream(stream_id=stream_id, app_name=app_name)
    _streams[stream_id] = stream
    return stream


def get_stream(stream_id: str) -> DeploymentStream | None:
    """Get a stream by ID.

    Args:
        stream_id: Stream identifier

    Returns:
        DeploymentStream if found, None otherwise
    """
    return _streams.get(stream_id)


def cleanup_old_streams() -> None:
    """Remove streams older than TTL."""
    now = datetime.now(UTC)
    expired = [
        sid
        for sid, stream in _streams.items()
        if (now - stream.created_at).total_seconds() > STREAM_TTL_SECONDS
    ]
    for sid in expired:
        del _streams[sid]


def get_current_stream() -> DeploymentStream | None:
    """Get the current stream context for this thread."""
    return getattr(_local, "current_stream", None)


@contextmanager
def stream_context(stream: DeploymentStream):
    """Context manager to set the current stream for logging.

    All log() calls within this context will be routed to the stream.
    Uses thread-local storage so concurrent deployments don't interleave logs.

    Args:
        stream: The stream to route logs to

    Example:
        stream = create_stream("myapp")
        with stream_context(stream):
            log("Building...")  # Goes to stream
            do_deploy(app)
        stream.finish(success=True)
    """
    old_stream = getattr(_local, "current_stream", None)
    _local.current_stream = stream
    try:
        yield stream
    finally:
        _local.current_stream = old_stream
