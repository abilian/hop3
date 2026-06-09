# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Tests for pressure-gated, cache-preserving disk reclaim on targets.

The disk filler in nightly runs is accumulated build cache + per-app
artifacts. ensure_disk_headroom must reclaim *ephemeral* artifacts only
when under pressure, keep the warm cache, and fail fast (clear error) when
the target is genuinely out of disk.
"""

from __future__ import annotations

import pytest
from hop3_testing.exceptions import TargetOutOfDiskError
from hop3_testing.targets.base import DeploymentTarget


class _FakeTarget(DeploymentTarget):
    """Target whose `df` returns scripted used%; records exec_run commands."""

    def __init__(self, used_pct_seq: list[int]) -> None:
        super().__init__()
        self._used_seq = list(used_pct_seq)
        self.commands: list[str] = []

    def start(self):  # pragma: no cover - not exercised
        raise NotImplementedError

    def stop(self) -> None:  # pragma: no cover - not exercised
        pass

    def exec_run(self, cmd):
        self.commands.append(cmd)
        if cmd.startswith("df "):
            used = self._used_seq.pop(0)
            free = 100 - used
            return (0, f"overlay 1000 {used * 10} {free * 10} {used}% /home/hop3\n", "")
        return (0, "", "")

    def _docker_cmds(self) -> list[str]:
        return [c for c in self.commands if c.startswith("docker")]


def test_no_reclaim_when_disk_has_headroom():
    target = _FakeTarget(used_pct_seq=[50])  # 50% free, well above threshold
    target.ensure_disk_headroom()
    assert target._docker_cmds() == []  # nothing pruned when there's room


def test_reclaim_under_pressure_preserves_warm_cache():
    # 10% free -> reclaim; recovers to 60% free.
    target = _FakeTarget(used_pct_seq=[90, 40])
    target.ensure_disk_headroom()

    docker = " ".join(target._docker_cmds())
    # Reclaims the ephemeral artifacts...
    assert "docker container prune -f" in docker
    assert "hop3/*" in docker  # unused per-app images (never cache) removed
    assert "docker image prune -f" in docker
    assert "docker builder prune -f --keep-storage=" in docker
    # ...but NEVER nukes base images or the whole cache at the gentle tier.
    assert "image prune -af" not in docker
    assert "image prune --all" not in docker
    assert "system prune" not in docker
    assert "builder prune -af" not in docker


def test_escalates_to_recover_before_failing():
    # 3% free, still 3% after the gentle tier -> escalate; then recovers to 30%.
    target = _FakeTarget(used_pct_seq=[97, 97, 70])
    target.ensure_disk_headroom()  # must NOT raise — escalation recovered it
    docker = " ".join(target._docker_cmds())
    assert "docker image prune -af" in docker  # escalation sacrificed base + cache
    assert "docker builder prune -af" in docker


def test_raises_when_still_out_of_disk_after_full_reclaim():
    # 3% free before, after gentle, AND after escalation -> genuinely out of disk.
    target = _FakeTarget(used_pct_seq=[97, 97, 97])
    with pytest.raises(TargetOutOfDiskError):
        target.ensure_disk_headroom()


def test_unreadable_df_is_a_noop():
    class _NoDf(_FakeTarget):
        def exec_run(self, cmd):
            self.commands.append(cmd)
            return (1, "", "df: not found")  # df fails

    target = _NoDf(used_pct_seq=[])
    target.ensure_disk_headroom()  # must not raise
    assert target._docker_cmds() == []
