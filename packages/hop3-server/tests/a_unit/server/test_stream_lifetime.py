# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
A stream outlives the TTL while its producer is still writing.

Deploy streams are bounded by their own build, so expiry by age was safe.
`hop3 run` is not bounded by anything: it runs whatever the operator asked
for, for as long as that takes.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from hop3.server import streaming
from hop3.server.streaming import (
    STREAM_LOG_BUFFER,
    cleanup_old_streams,
    create_stream,
    get_stream,
)


def age(stream, seconds: int) -> None:
    stream.created_at = datetime.now(UTC) - timedelta(seconds=seconds)


class TestCleanupKeepsWhatIsStillRunning:
    def test_a_running_stream_survives_the_ttl(self) -> None:
        """Dropping it would 404 a reconnect and lose the outcome."""
        stream = create_stream("long-job")
        age(stream, streaming.STREAM_TTL_SECONDS + 60)
        cleanup_old_streams()
        assert get_stream(stream.stream_id) is stream

    def test_a_finished_stream_is_still_collected(self) -> None:
        stream = create_stream("done-job")
        stream.finish(success=True)
        age(stream, streaming.STREAM_TTL_SECONDS + 60)
        cleanup_old_streams()
        assert get_stream(stream.stream_id) is None

    def test_a_recent_finished_stream_is_kept_for_replay(self) -> None:
        stream = create_stream("recent-job")
        stream.finish(success=True)
        cleanup_old_streams()
        assert get_stream(stream.stream_id) is stream


class TestTheLogBufferHasACeiling:
    def test_a_chatty_job_does_not_grow_without_limit(self) -> None:
        stream = create_stream("chatty")
        for i in range(STREAM_LOG_BUFFER + 500):
            stream.write(f"line {i}")
        assert len(stream.logs) == STREAM_LOG_BUFFER

    def test_the_newest_lines_are_the_ones_kept(self) -> None:
        """A late subscriber wants where the job is now, not where it began."""
        stream = create_stream("chatty")
        for i in range(STREAM_LOG_BUFFER + 500):
            stream.write(f"line {i}")
        assert stream.logs[-1].msg == f"line {STREAM_LOG_BUFFER + 499}"

    def test_the_reported_count_is_what_was_written(self, monkeypatch) -> None:
        """Not what survived the trim — the status would understate the job."""
        stream = create_stream("chatty")
        for i in range(STREAM_LOG_BUFFER + 500):
            stream.write(f"line {i}")
        assert stream.get_status()["log_count"] == STREAM_LOG_BUFFER + 500


class TestASubscriberCanArriveMidJob:
    """
    Catch-up replay runs while the producer thread is still writing. A list
    tolerated that; a deque raises `RuntimeError: deque mutated during
    iteration`, which killed the SSE generator before it sent a single event
    and reached the operator as "Stream ended unexpectedly. Check server
    logs." on an otherwise fine deploy.
    """

    def test_replay_survives_a_write_arriving_mid_catch_up(self) -> None:
        stream = create_stream("busy")
        for i in range(20):
            stream.write(f"line {i}")
        stream.finish(success=True)

        async def consume() -> list[str]:
            events = []
            async for event in stream.subscribe():
                # Stand in for the producer thread, which goes on appending
                # while the consumer is awaited between yields.
                stream.write("arrived during replay")
                events.append(event)
            return events

        events = asyncio.run(consume())
        assert any("line 0" in event for event in events)
        assert events[-1].startswith("event: complete")

    def test_a_finished_stream_replays_and_completes(self) -> None:
        stream = create_stream("done")
        stream.write("only line")
        stream.finish(success=True)

        async def consume() -> list[str]:
            return [event async for event in stream.subscribe()]

        events = asyncio.run(consume())
        assert any("only line" in event for event in events)
        assert events[-1].startswith("event: complete")
