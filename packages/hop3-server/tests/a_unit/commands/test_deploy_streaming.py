# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
What the streaming deploy tells the operator about the build queue.

A deploy that is waiting for a slot, and a deploy that was refused one, both
look identical to a deploy that has stalled unless they say otherwise — and
the only place the operator is looking is the stream they were just handed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hop3.commands import _deploy
from hop3.deployers.build_queue import BuildQueueFullError
from hop3.server.streaming import get_stream

if TYPE_CHECKING:
    from collections.abc import Callable


class StubQueue:
    """A build queue that records the job instead of running it."""

    def __init__(self, *, ahead: int = 0, full: bool = False) -> None:
        self.workers = 2
        self.ahead = ahead
        self.full = full
        self.submitted: Callable[[], None] | None = None

    def submit(self, job: Callable[[], None]) -> int:
        if self.full:
            msg = "Deployer can't start this build: the wait line is full"
            raise BuildQueueFullError(msg)
        self.submitted = job
        return self.ahead


@pytest.fixture
def stub_queue(monkeypatch) -> Callable[..., StubQueue]:
    def install(**kwargs) -> StubQueue:
        queue = StubQueue(**kwargs)
        monkeypatch.setattr(_deploy, "get_build_queue", lambda: queue)
        return queue

    return install


def test_a_deploy_that_starts_at_once_says_nothing_about_queueing(stub_queue):
    queue = stub_queue(ahead=0)

    result = _deploy.deploy_app_streaming("myapp", 1)

    log_stream = get_stream(result["stream_id"])
    assert queue.submitted is not None
    assert not log_stream.complete
    assert not [entry for entry in log_stream.logs if "Waiting" in entry.msg]


def test_a_queued_deploy_says_it_is_waiting(stub_queue):
    stub_queue(ahead=5)

    result = _deploy.deploy_app_streaming("myapp", 1)

    log_stream = get_stream(result["stream_id"])
    waiting = [
        entry for entry in log_stream.logs if "Waiting for a build slot" in entry.msg
    ]
    assert len(waiting) == 1
    # 5 ahead, 2 of them building: 3 deploys in the line before this one.
    assert "3 deploy(s) are ahead" in waiting[0].msg
    assert not log_stream.complete


def test_a_refused_deploy_fails_the_stream_rather_than_hanging(stub_queue):
    queue = stub_queue(full=True)

    result = _deploy.deploy_app_streaming("myapp", 1)

    log_stream = get_stream(result["stream_id"])
    assert queue.submitted is None
    # Finished, failed, and carrying the reason: a client connecting after the
    # fact replays a complete stream, so this reaches it either way.
    assert log_stream.complete
    assert not log_stream.success
    assert "wait line is full" in log_stream.error_message
