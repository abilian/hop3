# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""What a command Hop3 runs on the app's behalf says must reach the operator."""

from __future__ import annotations

from hop3.lib import log_command_stream
from hop3.lib.console import capture_logs


class TestBeforeRunOutputIsSurfaced:
    """
    A before-run command's output must reach the operator, pass or fail.

    It was shown only when the command FAILED. These commands are the app's
    headless bootstrap, and a successful one still reports what it did — which
    account it created, or that it found one already and left it alone. Uptime
    Kuma's says outright when the admin Hop3 is about to advertise does not
    exist in its database; that line was printed on every deploy and read by
    nobody, while the smoke test's "the credential Hop3 generated was refused"
    sent three rounds of investigation at the application instead.
    """

    def test_stdout_of_a_successful_command_is_shown(self) -> None:
        with capture_logs(verbosity=3) as captured:
            log_command_stream("stdout", "admin 'admin' created.", level=1)

        messages = [e["msg"] for e in captured.get_logs()]
        assert any("admin 'admin' created." in m for m in messages)

    def test_stderr_of_a_successful_command_is_shown(self) -> None:
        """A zero exit with stderr is a warning the script chose to raise."""
        with capture_logs(verbosity=3) as captured:
            log_command_stream("stderr", "WARNING: the admin does NOT exist", level=0)

        messages = [e["msg"] for e in captured.get_logs()]
        assert any("does NOT exist" in m for m in messages)

    def test_an_empty_stream_prints_no_header(self) -> None:
        """Most commands say nothing; they must not add a blank section."""
        with capture_logs(verbosity=3) as captured:
            log_command_stream("stdout", "", level=1)
            log_command_stream("stderr", None, level=1)
            log_command_stream("stdout", "   \n  \n", level=1)

        assert captured.get_logs() == []

    def test_a_flood_is_tailed_not_dropped(self) -> None:
        """The last lines are where a script says what it concluded."""
        with capture_logs(verbosity=3) as captured:
            log_command_stream("stdout", "\n".join(str(n) for n in range(100)), level=1)

        shown = [e["msg"].strip().lstrip("->").strip() for e in captured.get_logs()][1:]
        assert shown == [str(n) for n in range(80, 100)]
