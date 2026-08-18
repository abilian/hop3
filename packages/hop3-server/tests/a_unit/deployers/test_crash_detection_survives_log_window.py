# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Crash detection must keep working after the log fills its window.

`_wait_for_app_start` fails fast once it has seen three crash indicators, so a
crash-looping app should be given up on in seconds. It was not: keycloak spent
its full 420-second budget, and mattermost its 60, waiting on an x86-64 binary
that could never execute on an arm64 host — with `throttling` in the log the
entire time, and the post-mortem diagnosis correctly reporting it afterwards.

The counting was the bug. `_process_new_logs` kept a running total of lines seen
and compared it against `len(app.get_logs(lines=50))` — but that returns the
*last* 50 lines, a rolling window. Once a chatty startup passed 50 lines the
total caught up with the window and `len(logs) <= seen` was true forever after.
Nothing was ever new again, so no indicator was ever counted and the fail-fast
could not fire. The window's size decided how long detection lasted.

So compare content, not counts.
"""

from __future__ import annotations

from hop3.deployers.deployer import (
    _is_crash_indicator,
    _lines_since,
    _process_new_logs,
)


class _App:
    """An app whose log is a rolling window over an ever-growing stream."""

    name = "chatty"

    def __init__(self, stream: list[str]) -> None:
        self.stream = stream

    def get_logs(self, lines: int = 50) -> list[str]:
        return self.stream[-lines:]


def test_new_lines_are_whatever_extends_past_the_overlap():
    previous = ["a", "b", "c"]
    current = ["b", "c", "d", "e"]

    assert _lines_since(previous, current) == ["d", "e"]


def test_an_unchanged_window_yields_nothing():
    window = ["a", "b", "c"]

    assert _lines_since(window, window) == []


def test_everything_is_new_when_the_window_jumped():
    """A log rotation, or more output than the window holds between polls."""
    assert _lines_since(["a", "b"], ["x", "y"]) == ["x", "y"]


def test_the_first_poll_sees_everything():
    assert _lines_since([], ["a", "b"]) == ["a", "b"]


def test_crashes_are_still_detected_once_the_window_is_full():
    """
    The regression, at the scale it actually happened.

    A crash-looping app logs steadily. By the time it emits its throttling
    lines, the 50-line window has long since filled — which is precisely when
    detection used to stop.
    """
    stream = [f"line {i}" for i in range(200)]
    app = _App(stream)

    seen, crashes = _process_new_logs(app, [])
    assert crashes == 0

    # The app now crash-loops, well past the window's size.
    stream.extend(["uWSGI throttling worker respawn"] * 3)
    _seen, crashes = _process_new_logs(app, seen)

    assert crashes == 3, "the fail-fast needs three indicators to trigger"


def test_a_burst_larger_than_the_display_cap_is_fully_counted():
    """Only ten lines are printed; all of them must still be counted."""
    stream = [f"line {i}" for i in range(40)]
    app = _App(stream)
    seen, _ = _process_new_logs(app, [])

    stream.extend(["segmentation fault"] * 12)
    _seen, crashes = _process_new_logs(app, seen)

    assert crashes == 12


def test_the_loader_error_reaches_the_counter_via_throttling():
    """
    What the arm64 failures actually logged.

    The loader message itself is not a crash pattern — uWSGI's reaction to it
    is, and that is what repeats.
    """
    assert not _is_crash_indicator("OrbStack ERROR: Dynamic loader not found")
    assert _is_crash_indicator("...throttling for 3 seconds...")
