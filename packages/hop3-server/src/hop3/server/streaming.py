# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Server-Sent Events streaming for deployment logs.

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
from collections import deque
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Generator

# Stream registry
_streams: dict[str, DeploymentStream] = {}
STREAM_TTL_SECONDS = 3600  # 1 hour

#: Log entries kept for replay to a client that connects late. A deploy is
#: bounded by its own build; `hop3 run` is not — it runs whatever the operator
#: asked for, for as long as that takes — so the buffer needs a ceiling or one
#: chatty maintenance job grows the server's memory until it is killed. A live
#: subscriber still sees every line; only the replay is trimmed.
STREAM_LOG_BUFFER = 5000

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
    """
    Captures deployment logs and streams to connected clients.

    This class implements a pub/sub pattern where:
    - The deployment process writes logs via write()
    - Connected SSE clients subscribe via subscribe()
    - Logs are buffered so late-connecting clients can catch up
    """

    stream_id: str
    app_name: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    logs: deque[LogEntry] = field(
        default_factory=lambda: deque(maxlen=STREAM_LOG_BUFFER)
    )
    #: Total written, which `logs` stops counting once it is full.
    log_count: int = 0
    subscribers: list[asyncio.Queue] = field(default_factory=list)
    complete: bool = False
    success: bool = False
    error_message: str = ""
    #: What the client says when this finishes well. A deploy and a one-off
    #: command both stream through here, and "App deployed successfully" is a
    #: false claim about the second.
    success_message: str = ""
    # Event loop running the SSE consumer, captured on first subscribe().
    # write()/finish() run in the deployment's background OS thread, but
    # asyncio.Queue is NOT thread-safe: a bare cross-thread put_nowait() does
    # not wake the consumer's `await queue.get()`, so it only advances on its
    # keepalive timeout --- making every deploy appear to take ~30s. We route
    # puts back onto the loop with call_soon_threadsafe so they arrive at once.
    _loop: asyncio.AbstractEventLoop | None = field(default=None, repr=False)

    def write(self, msg: str, level: int = 0, fg: str = "") -> None:
        """
        Write a log entry and notify all subscribers.

        Args:
            msg: Log message
            level: Verbosity level (0=important, 1=normal, 2=verbose, 3=debug)
            fg: Color hint (green, red, blue, yellow, etc.)
        """
        entry = LogEntry(msg=msg, level=level, fg=fg)
        self.logs.append(entry)
        self.log_count += 1
        self._notify(("log", entry))

    def finish(
        self, success: bool, error_message: str = "", success_message: str = ""
    ) -> None:
        """
        Mark stream as complete.

        Args:
            success: Whether the job succeeded
            error_message: Error message if failed
            success_message: What the client should say if it succeeded;
                the client keeps its deploy wording when this is empty
        """
        self.complete = True
        self.success = success
        self.error_message = error_message
        if success_message:
            self.success_message = success_message
        self._notify(("complete", None))

    def _notify(self, item: tuple[str, Any]) -> None:
        """
        Push an event to every subscriber, waking the consumer's loop.

        Called from the deployment's background thread, so cross-thread puts
        must be scheduled on the consumer's event loop (see _loop above).
        Falls back to a direct put when no loop is captured (sync/test use).
        """
        loop = self._loop
        for queue in self.subscribers:
            if loop is not None and loop.is_running():
                loop.call_soon_threadsafe(self._safe_put, queue, item)
            else:
                self._safe_put(queue, item)

    @staticmethod
    def _safe_put(queue: asyncio.Queue, item: tuple[str, Any]) -> None:
        # Skip slow consumers rather than block the producer.
        with suppress(asyncio.QueueFull):
            queue.put_nowait(item)

    async def subscribe(self) -> AsyncIterator[str]:
        """
        Subscribe to this stream and yield SSE-formatted events.

        Yields:
            SSE-formatted strings ready to send to client
        """
        # Capture the loop so background-thread writers can wake us (_notify).
        self._loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self.subscribers.append(queue)

        try:
            # First, send all existing logs (catch-up). Snapshot it: the
            # producer is a live thread still appending, and a deque raises
            # `RuntimeError: deque mutated during iteration` where a list
            # quietly tolerated it — which killed the generator mid-catch-up
            # and surfaced to the operator as "Stream ended unexpectedly".
            for entry in list(self.logs):
                yield entry.to_sse()

            # If already complete, send completion event and return
            if self.complete:
                yield self._completion_event()
                return

            # Stream new logs as they arrive
            while True:
                try:
                    event_type, data = await asyncio.wait_for(queue.get(), timeout=30.0)
                except TimeoutError:
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
            "success_message": self.success_message,
            "duration": duration,
            "log_count": self.log_count,
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
            "log_count": self.log_count,
            "subscriber_count": len(self.subscribers),
            "created_at": self.created_at.isoformat(),
            "duration": (datetime.now(UTC) - self.created_at).total_seconds(),
        }


def create_stream(app_name: str) -> DeploymentStream:
    """
    Create a new deployment stream.

    Args:
        app_name: Name of the app being deployed

    Returns:
        New DeploymentStream instance
    """
    # Clean up old streams first
    cleanup_old_streams()

    # Full UUID: 122 bits of entropy, not enumerable. The previous
    # 8-hex-char slice had only 2**32 combinations, trivially brute-forced
    # once the endpoint was publicly reachable. Combined with the deployer
    # role guard on StreamController this gives layered defense: an attacker
    # needs a deployer's token *and* a lucky guess.
    stream_id = str(uuid.uuid4())
    stream = DeploymentStream(stream_id=stream_id, app_name=app_name)
    _streams[stream_id] = stream
    return stream


def get_stream(stream_id: str) -> DeploymentStream | None:
    """
    Get a stream by ID.

    Args:
        stream_id: Stream identifier

    Returns:
        DeploymentStream if found, None otherwise
    """
    return _streams.get(stream_id)


def cleanup_old_streams() -> None:
    """Remove streams older than TTL."""
    now = datetime.now(UTC)
    # A stream that has not finished is still being written to: its producer
    # thread is alive and a client may be watching. `hop3 run` made that
    # reachable — a maintenance job can outlive the TTL, and dropping its
    # stream mid-run would 404 any reconnect and lose the outcome.
    expired = [
        sid
        for sid, stream in _streams.items()
        if stream.complete
        and (now - stream.created_at).total_seconds() > STREAM_TTL_SECONDS
    ]
    for sid in expired:
        del _streams[sid]


def get_current_stream() -> DeploymentStream | None:
    """Get the current stream context for this thread."""
    return getattr(_local, "current_stream", None)


@contextmanager
def stream_context(stream: DeploymentStream) -> Generator[DeploymentStream, None, None]:
    """
    Context manager to set the current stream for logging.

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


def has_active_deploy(app_name: str) -> bool:
    """
    Is a deploy currently in flight for ``app_name``?

    The app's row still reads STOPPED while a deploy builds (there is no
    DEPLOYING run_state — the FSM tracks the *process*, not the build), so the
    dashboard asks this to avoid reporting a multi-minute build as "STOPPED",
    which reads as "nothing is happening".
    """
    return any(
        stream.app_name == app_name and not stream.complete
        for stream in _streams.values()
    )
