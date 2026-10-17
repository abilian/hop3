# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""ContainerTarget adapter — exec_run demux fidelity (no Docker)."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from itertools import count

import pytest
from hop3_testing.exceptions import CommandTimeoutError
from hop3_testing.targets import base
from hop3_testing.targets.adapter import ContainerTarget


@dataclass
class _FakeExecResult:
    exit_code: int
    output: tuple[bytes | None, bytes | None]


class _FakeContainer:
    """Records the exec_run call and returns a canned demux result."""

    def __init__(self, result: _FakeExecResult) -> None:
        self.result = result
        self.calls: list[tuple] = []

    def exec_run(self, cmd, *, demux, user):
        self.calls.append((cmd, demux, user))
        return self.result


def test_exec_run_demuxes_stdout() -> None:
    container = _FakeContainer(_FakeExecResult(0, (b"hi\n", None)))
    target = ContainerTarget(container)
    assert target.exec_run("echo hi") == (0, "hi\n", "")
    # Shell-wrapped and run as root (review #1), under the target's ceiling.
    ((argv, demux, user),) = container.calls
    assert (argv[:2], demux, user) == (["bash", "-c"], True, "root")
    assert shlex.split(argv[2]) == [
        "timeout", "-k", "10", "300", "bash", "-c", "echo hi",
    ]  # fmt: skip


def test_exec_run_separates_stderr_and_exit_code() -> None:
    container = _FakeContainer(_FakeExecResult(2, (b"out", b"boom")))
    target = ContainerTarget(container)
    assert target.exec_run("false") == (2, "out", "boom")


def test_exec_run_joins_list_input() -> None:
    container = _FakeContainer(_FakeExecResult(0, (b"", None)))
    target = ContainerTarget(container)
    target.exec_run(["echo", "a b", "c'd"])
    # shlex.join preserves the args through both shells.
    inner = shlex.split(container.calls[0][0][2])[-1]
    assert shlex.split(inner) == ["echo", "a b", "c'd"]


def test_exec_run_handles_none_output() -> None:
    container = _FakeContainer(_FakeExecResult(0, (None, None)))
    target = ContainerTarget(container)
    assert target.exec_run("true") == (0, "", "")


def test_a_command_past_its_ceiling_raises_with_its_output(monkeypatch) -> None:
    """A hung command left the run silent, with no error, for as long as it hung."""
    clock = count(step=60)
    monkeypatch.setattr(base.time, "monotonic", lambda: next(clock))
    container = _FakeContainer(_FakeExecResult(124, (b"step 1\nstep 2\n", None)))

    with pytest.raises(CommandTimeoutError, match="within 30s") as excinfo:
        ContainerTarget(container).exec_run("sleep 99", timeout=30)

    assert "`sleep 99`" in str(excinfo.value)
    assert "step 2" in str(excinfo.value)


def test_a_quick_exit_124_is_the_commands_own_status(monkeypatch) -> None:
    monkeypatch.setattr(base.time, "monotonic", lambda: 0.0)
    container = _FakeContainer(_FakeExecResult(124, (b"", None)))

    assert ContainerTarget(container).exec_run("exit 124", timeout=30)[0] == 124
