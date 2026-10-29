# Copyright (c) 2023-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Tests for deployment-log streaming identifiers (Wave 2 security fix).

Primary defense for the SSE endpoint lives at the controller: StreamController
now requires the deployer role, so a token is needed. The stream_id change below is
the secondary defense --- make the identifier unguessable even if an attacker
already has a valid token.
"""

from __future__ import annotations

import asyncio
import threading
import uuid

import pytest

from hop3.server.streaming import create_stream, get_stream


def test_stream_id_is_full_uuid() -> None:
    """
    stream_id must be a full UUIDv4 string (36 chars), not the old
    truncated 8-hex-char value. 2**32 combinations is trivial to brute
    force once the endpoint is reachable.
    """
    stream = create_stream("testapp")

    # Full UUIDv4 canonical form is 36 chars including hyphens.
    assert len(stream.stream_id) == 36
    # Must parse back to a real UUID (raises otherwise).
    parsed = uuid.UUID(stream.stream_id)
    assert parsed.version == 4


def test_stream_ids_are_unique() -> None:
    """
    Two streams created back-to-back don't collide. Cheap sanity
    check that we didn't accidentally freeze the UUID source.
    """
    ids = {create_stream(f"app{i}").stream_id for i in range(50)}
    assert len(ids) == 50


def test_get_stream_finds_created_stream() -> None:
    """Round-trip: create a stream and look it up by id."""
    stream = create_stream("testapp")
    found = get_stream(stream.stream_id)
    assert found is stream


def test_get_stream_unknown_id_returns_none() -> None:
    """Guessing a stream id returns None; controller maps to 404."""
    assert get_stream("not-a-real-uuid") is None
    assert get_stream(str(uuid.uuid4())) is None


@pytest.mark.asyncio
async def test_cross_thread_notify_is_scheduled_on_the_loop() -> None:
    """
    write()/finish() from the deploy's background OS thread must be routed
    onto the consumer's event loop via ``call_soon_threadsafe``.

    Regression: asyncio.Queue is not thread-safe. A bare cross-thread
    ``put_nowait()`` does not wake the consumer's ``await queue.get()``, so the
    SSE consumer only advanced when its ``wait_for(..., timeout=30.0)`` keepalive
    fired --- making every deployment appear to take ~30s regardless of the real
    work (~2s). This asserts the producer hands the put to the loop instead of
    poking the queue directly from the foreign thread.
    """
    loop = asyncio.get_running_loop()
    scheduled: list[object] = []
    real_call_soon_threadsafe = loop.call_soon_threadsafe

    def spy(callback, *args):
        scheduled.append(callback)
        return real_call_soon_threadsafe(callback, *args)

    setattr(loop, "call_soon_threadsafe", spy)  # ruff:ignore[set-attr-with-constant]
    try:
        stream = create_stream("threadtest")
        queue: asyncio.Queue = asyncio.Queue(maxsize=10)
        stream.subscribers.append(queue)
        stream._loop = loop  # what subscribe() captures on the live path

        # write() from a real background thread, exactly like the deploy thread.
        thread = threading.Thread(target=lambda: stream.write("building..."))
        thread.start()
        thread.join()

        # The foreign-thread write was scheduled on the loop, not put directly.
        assert scheduled, "cross-thread write must use call_soon_threadsafe"

        # ...and the event is delivered to the (loop-side) consumer.
        kind, entry = await asyncio.wait_for(queue.get(), timeout=5.0)
        assert kind == "log"
        assert entry.msg == "building..."
    finally:
        setattr(loop, "call_soon_threadsafe", real_call_soon_threadsafe)  # ruff:ignore[set-attr-with-constant]


def _drain(queue: asyncio.Queue) -> list[tuple[str, object]]:
    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return items


def test_completion_reaches_a_subscriber_whose_queue_is_full() -> None:
    """Regression: QueueFull dropped `complete`, so the client never ended."""
    stream = create_stream("slowclient")
    queue: asyncio.Queue = asyncio.Queue(maxsize=3)
    stream.subscribers.append(queue)
    for i in range(5):
        stream.write(f"line {i}")

    stream.finish(success=True)

    items = _drain(queue)
    assert items[-1] == ("complete", None)
    kind, marker = items[-2]
    assert kind == "log"
    assert "dropped" in marker.msg


def test_dropped_lines_are_reported_where_they_were_lost() -> None:
    stream = create_stream("slowclient")
    queue: asyncio.Queue = asyncio.Queue(maxsize=2)
    stream.subscribers.append(queue)
    for i in range(5):  # two fit, three are dropped
        stream.write(f"line {i}")
    _drain(queue)

    stream.write("line 5")

    assert [entry.msg for _, entry in _drain(queue)] == [
        "[3 log line(s) dropped: this client fell behind the stream]",
        "line 5",
    ]


def test_lines_evicted_for_completion_are_marked_where_they_were() -> None:
    """The oldest lines make room for `complete`; their marker comes first."""
    stream = create_stream("slowclient")
    queue: asyncio.Queue = asyncio.Queue(maxsize=4)
    stream.subscribers.append(queue)
    for i in range(4):
        stream.write(f"line {i}")

    stream.finish(success=True)

    items = _drain(queue)
    assert [entry.msg for _, entry in items[:-1]] == [
        "[2 log line(s) dropped: this client fell behind the stream]",
        "line 2",
        "line 3",
    ]
    assert items[-1] == ("complete", None)


def test_both_gaps_are_marked_in_place() -> None:
    """Lines refused earlier were the newest: their marker follows the kept."""
    stream = create_stream("slowclient")
    queue: asyncio.Queue = asyncio.Queue(maxsize=4)
    stream.subscribers.append(queue)
    for i in range(6):  # four fit, two are refused
        stream.write(f"line {i}")

    stream.finish(success=True)

    assert [entry.msg if kind == "log" else kind for kind, entry in _drain(queue)] == [
        "[3 log line(s) dropped: this client fell behind the stream]",
        "line 3",
        "[2 log line(s) dropped: this client fell behind the stream]",
        "complete",
    ]


@pytest.mark.asyncio
async def test_a_waiting_subscriber_ends_when_the_stream_is_complete(
    monkeypatch,
) -> None:
    """Regression: the keepalive branch never looked at `complete`."""
    monkeypatch.setattr("hop3.server.streaming.KEEPALIVE_SECONDS", 0.01)
    stream = create_stream("lostevent")
    events = stream.subscribe()
    first = asyncio.ensure_future(anext(events))
    await asyncio.sleep(0.02)  # subscribed, waiting, one keepalive sent
    assert first.result() == ": keepalive\n\n"

    # Finished without its event reaching this queue.
    stream.complete = True
    stream.success = True

    event = await asyncio.wait_for(anext(events), timeout=1.0)
    assert event.startswith("event: complete")
