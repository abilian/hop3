# Copyright (c) 2023-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for deployment-log streaming identifiers (Wave 2 security fix).

Primary defense for the SSE endpoint lives at the controller: StreamController
now requires auth_guard, so a token is needed. The stream_id change below is
the secondary defense --- make the identifier unguessable even if an attacker
already has a valid token.
"""

from __future__ import annotations

import uuid

from hop3.server.streaming import create_stream, get_stream


def test_stream_id_is_full_uuid() -> None:
    """stream_id must be a full UUIDv4 string (36 chars), not the old
    truncated 8-hex-char value. 2**32 combinations is trivial to brute
    force once the endpoint is reachable."""
    stream = create_stream("testapp")

    # Full UUIDv4 canonical form is 36 chars including hyphens.
    assert len(stream.stream_id) == 36
    # Must parse back to a real UUID (raises otherwise).
    parsed = uuid.UUID(stream.stream_id)
    assert parsed.version == 4


def test_stream_ids_are_unique() -> None:
    """Two streams created back-to-back don't collide. Cheap sanity
    check that we didn't accidentally freeze the UUID source."""
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
