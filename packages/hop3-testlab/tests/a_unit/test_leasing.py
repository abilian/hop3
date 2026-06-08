# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""The run lease (ADR 044 §D) — acquire / contend / release / expire."""

from __future__ import annotations

from hop3_testlab import leasing
from hop3_testlab.config import TestlabConfig
from hop3_testlab.db import get_session_factory


def _session():
    return get_session_factory(str(TestlabConfig.get_instance().DB_PATH))()


def test_acquire_then_busy_then_release():
    with _session() as s:
        assert leasing.try_acquire(s, "docker", "A") is True
    with _session() as s:
        assert leasing.try_acquire(s, "docker", "B") is False  # held by A
    with _session() as s:
        leasing.release(s, "docker", "A")
    with _session() as s:
        assert leasing.try_acquire(s, "docker", "B") is True  # free again


def test_expired_lease_is_reclaimable():
    with _session() as s:
        assert leasing.try_acquire(s, "docker", "A", ttl_seconds=0) is True
    with _session() as s:
        # A's lease expired immediately (ttl=0), so B can take it.
        assert leasing.try_acquire(s, "docker", "B") is True


def test_release_by_non_holder_is_noop():
    with _session() as s:
        assert leasing.try_acquire(s, "docker", "A") is True
    with _session() as s:
        leasing.release(s, "docker", "B")  # B doesn't hold it
    with _session() as s:
        assert leasing.try_acquire(s, "docker", "C") is False  # A still holds it


def test_set_pid_records_on_the_lease():
    with _session() as s:
        leasing.try_acquire(s, "docker", "A")
    with _session() as s:
        leasing.set_pid(s, "docker", 4242)
    with _session() as s:
        lease = leasing.current_lease(s)
        assert lease is not None
        assert lease.pid == 4242


def test_current_lease_returns_live_one_and_none_when_idle():
    with _session() as s:
        assert leasing.current_lease(s) is None  # nothing running
    with _session() as s:
        leasing.try_acquire(s, "1.2.3.4", "A")
    with _session() as s:
        lease = leasing.current_lease(s)
        assert lease is not None
        assert lease.target_id == "1.2.3.4"


def test_current_lease_ignores_expired():
    with _session() as s:
        leasing.try_acquire(s, "docker", "A", ttl_seconds=0)  # already expired
    with _session() as s:
        assert leasing.current_lease(s) is None


def test_force_release_drops_regardless_of_holder():
    with _session() as s:
        leasing.try_acquire(s, "docker", "A")
    with _session() as s:
        leasing.force_release(s, "docker")  # the web app isn't holder "A"
    with _session() as s:
        assert leasing.current_lease(s) is None
        assert leasing.try_acquire(s, "docker", "B") is True  # free again
