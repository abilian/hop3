# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""ContainerTarget adapter — exec_run demux fidelity (no Docker)."""

from __future__ import annotations

from dataclasses import dataclass

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
    # Shell-wrapped and run as root (review #1).
    assert container.calls == [(["bash", "-c", "echo hi"], True, "root")]


def test_exec_run_separates_stderr_and_exit_code() -> None:
    container = _FakeContainer(_FakeExecResult(2, (b"out", b"boom")))
    target = ContainerTarget(container)
    assert target.exec_run("false") == (2, "out", "boom")


def test_exec_run_joins_list_input() -> None:
    container = _FakeContainer(_FakeExecResult(0, (b"", None)))
    target = ContainerTarget(container)
    target.exec_run(["echo", "a b", "c'd"])
    # shlex.join preserves the args through the shell.
    assert container.calls[0][0] == ["bash", "-c", "echo 'a b' 'c'\"'\"'d'"]


def test_exec_run_handles_none_output() -> None:
    container = _FakeContainer(_FakeExecResult(0, (None, None)))
    target = ContainerTarget(container)
    assert target.exec_run("true") == (0, "", "")
