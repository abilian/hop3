# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Running a command and handing back its output as it arrives.

`hop3 run` used to capture everything and return it at the end, under a
five-minute timeout. A maintenance job that legitimately runs longer was
killed mid-work and reported as a read timeout naming a localhost port; and
until it finished there was nothing to look at, so a job that was working and
a job that was wedged looked the same.
"""

from __future__ import annotations

import sys
import time

import pytest

from hop3.lib.util import CommandNotFoundError, stream_command


def collect() -> tuple[list[str], object]:
    lines: list[str] = []
    return lines, lines.append


class TestOutputArrivesLineByLine:
    def test_each_line_is_handed_over(self) -> None:
        lines, on_line = collect()
        code = stream_command(
            [sys.executable, "-c", "print('one'); print('two'); print('three')"],
            on_line=on_line,
        )
        assert lines == ["one", "two", "three"]
        assert code == 0

    def test_it_does_not_wait_for_the_process_to_exit(self) -> None:
        """The whole point: a long job shows progress while it is running."""
        seen_at: list[float] = []
        start = time.monotonic()
        stream_command(
            [
                sys.executable,
                "-u",
                "-c",
                "import time; print('early'); time.sleep(0.6); print('late')",
            ],
            on_line=lambda _line: seen_at.append(time.monotonic() - start),
        )
        assert len(seen_at) == 2
        assert seen_at[0] < 0.3, "the first line waited for the second"
        assert seen_at[1] >= 0.5

    def test_a_child_that_would_block_buffer_still_streams(self) -> None:
        """
        A Python child writing to a pipe block-buffers by default, so its
        output would arrive only at exit — which looks exactly like no
        streaming at all. PYTHONUNBUFFERED is forced for that reason.
        """
        seen_at: list[float] = []
        start = time.monotonic()
        stream_command(
            [
                sys.executable,
                "-c",
                "import time; print('early'); time.sleep(0.6); print('late')",
            ],
            on_line=lambda _line: seen_at.append(time.monotonic() - start),
            env={"PATH": "/usr/bin:/bin"},
        )
        assert seen_at[0] < 0.3

    def test_stderr_is_interleaved_in_the_order_printed(self) -> None:
        """Splitting the streams only makes sense when both are shown whole."""
        lines, on_line = collect()
        stream_command(
            [
                sys.executable,
                "-u",
                "-c",
                (
                    "import sys; print('out1'); "
                    "print('err', file=sys.stderr); print('out2')"
                ),
            ],
            on_line=on_line,
        )
        assert lines == ["out1", "err", "out2"]


class TestTheOutcome:
    def test_a_failing_command_returns_its_exit_code(self) -> None:
        lines, on_line = collect()
        code = stream_command(
            [sys.executable, "-c", "print('before'); raise SystemExit(3)"],
            on_line=on_line,
        )
        assert code == 3
        assert lines == ["before"], "output before the failure is not lost"

    def test_a_missing_executable_is_named(self) -> None:
        _lines, on_line = collect()
        with pytest.raises(CommandNotFoundError) as excinfo:
            stream_command(["definitely-not-a-real-binary"], on_line=on_line)
        assert "definitely-not-a-real-binary" in str(excinfo.value)

    def test_stdin_data_reaches_the_command(self) -> None:
        lines, on_line = collect()
        stream_command(
            [sys.executable, "-c", "import sys; print(sys.stdin.read().strip())"],
            on_line=on_line,
            stdin_data="hunter2\n",
        )
        assert lines == ["hunter2"]

    def test_a_command_given_no_stdin_sees_eof(self) -> None:
        """Not the server's own stdin, and not a hang waiting on a tty."""
        lines, on_line = collect()
        code = stream_command(
            [sys.executable, "-c", "import sys; print(repr(sys.stdin.read()))"],
            on_line=on_line,
        )
        assert code == 0
        assert lines == ["''"]


class TestItRunsWhereItIsTold:
    def test_the_working_directory_is_the_app_source(self, tmp_path) -> None:
        lines, on_line = collect()
        stream_command(
            [sys.executable, "-c", "import os; print(os.getcwd())"],
            on_line=on_line,
            cwd=tmp_path,
        )
        assert lines[0].endswith(tmp_path.name)

    def test_the_app_environment_is_passed(self, tmp_path) -> None:
        lines, on_line = collect()
        stream_command(
            [sys.executable, "-c", "import os; print(os.environ['DATABASE_URL'])"],
            on_line=on_line,
            env={"PATH": "/usr/bin:/bin", "DATABASE_URL": "postgres://x/y"},
        )
        assert lines == ["postgres://x/y"]
