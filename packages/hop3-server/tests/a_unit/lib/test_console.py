# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the console logging / coloring utilities."""

from __future__ import annotations

import pytest
from termcolor import colored

# `TestingConsole` is imported as `InMemoryConsole` so pytest does not try to
# collect the source class (its name starts with "Test") as a test case.
from hop3.lib.console import (
    Abort,
    CaptureLogs,
    CapturingConsole,
    PrintingConsole,
    TestingConsole as InMemoryConsole,
    VerbosityContext,
    blue,
    bold,
    cyan,
    debug,
    dim,
    echo,
    error,
    get_console,
    get_current_console,
    get_verbosity,
    green,
    info,
    log,
    magenta,
    panic,
    red,
    set_console,
    set_verbosity,
    success,
    warning,
    yellow,
)


class BoomError(Exception):
    """Sentinel exception used to verify context managers restore state."""


@pytest.fixture
def restore_console():
    """Restore the global console after a test mutates it."""
    saved = get_current_console()
    yield
    set_console(saved)


@pytest.fixture
def restore_verbosity():
    """Restore the global verbosity after a test mutates it."""
    saved = get_verbosity()
    yield
    set_verbosity(saved)


class TestColorHelpers:
    """The color helpers delegate to termcolor.colored."""

    @pytest.mark.parametrize(
        ("func", "name"),
        [
            (red, "red"),
            (green, "green"),
            (yellow, "yellow"),
            (blue, "blue"),
            (magenta, "magenta"),
            (cyan, "cyan"),
        ],
    )
    def test_color_matches_termcolor(self, func, name):
        assert func("hello") == colored("hello", name)

    def test_bold_uses_bold_attr(self):
        assert bold("hi") == colored("hi", attrs=["bold"])

    def test_dim_uses_dark_attr(self):
        assert dim("hi") == colored("hi", attrs=["dark"])


class TestSemanticAliases:
    """Semantic aliases point at the underlying color helpers."""

    def test_success_is_green(self):
        assert success is green

    def test_error_is_red(self):
        assert error is red

    def test_warning_is_yellow(self):
        assert warning is yellow

    def test_info_is_blue(self):
        assert info is blue

    def test_debug_is_dim(self):
        assert debug is dim


class TestPrintingConsole:
    """PrintingConsole.echo routes through the color branches and to stdout."""

    @pytest.mark.parametrize(
        ("fg", "transform"),
        [
            ("", lambda s: s),
            ("white", lambda s: s),
            ("green", green),
            ("red", red),
            ("blue", blue),
            ("yellow", yellow),
            ("cyan", cyan),
            ("magenta", magenta),
        ],
    )
    def test_echo_prints_with_color(self, capsys, fg, transform):
        console = PrintingConsole()

        console.echo("payload", fg=fg)

        captured = capsys.readouterr()
        assert captured.out == transform("payload") + "\n"

    def test_echo_unknown_color_raises_value_error(self):
        console = PrintingConsole()

        with pytest.raises(ValueError, match="Unknown color: purple"):
            console.echo("payload", fg="purple")

    def test_default_output_is_empty(self):
        # Inherited ABC default behavior.
        assert PrintingConsole().output() == ""

    def test_default_reset_is_a_noop(self):
        # PrintingConsole does not override reset(); the ABC default just passes.
        console = PrintingConsole()

        assert console.reset() is None


class TestTestingConsole:
    """TestingConsole captures messages into an in-memory buffer."""

    def test_echo_appends_to_buffer(self):
        console = InMemoryConsole()

        console.echo("one")
        console.echo("two", fg="red")

        assert console.buffer == ["one", "two"]

    def test_output_joins_with_newline(self):
        console = InMemoryConsole()
        console.echo("a")
        console.echo("b")

        assert console.output() == "a\nb"

    def test_reset_clears_buffer(self):
        console = InMemoryConsole()
        console.echo("a")

        console.reset()

        assert console.buffer == []
        assert console.output() == ""

    def test_separate_instances_have_separate_buffers(self):
        # The factory default must not be shared between instances.
        a = InMemoryConsole()
        b = InMemoryConsole()

        a.echo("only-a")

        assert a.buffer == ["only-a"]
        assert b.buffer == []


class TestCapturingConsole:
    """CapturingConsole records every message and prints by verbosity."""

    def test_echo_captures_msg_fg_and_level(self):
        console = CapturingConsole(verbosity=3)

        console.echo("hello", fg="red", level=2)

        assert console.buffer == [{"msg": "hello", "fg": "red", "level": 2}]

    def test_echo_prints_when_level_within_verbosity(self, capsys):
        console = CapturingConsole(verbosity=2)

        console.echo("shown", level=2)

        assert capsys.readouterr().out == "shown\n"

    def test_echo_suppresses_print_above_verbosity(self, capsys):
        console = CapturingConsole(verbosity=1)

        console.echo("hidden", level=2)

        # Still captured, just not printed.
        assert capsys.readouterr().out == ""
        assert console.buffer == [{"msg": "hidden", "fg": "", "level": 2}]

    def test_output_joins_messages_only(self):
        console = CapturingConsole()
        console.echo("a", level=0)
        console.echo("b", level=5)

        assert console.output() == "a\nb"

    def test_reset_clears_buffer(self):
        console = CapturingConsole()
        console.echo("a")

        console.reset()

        assert console.buffer == []

    def test_get_logs_returns_copy(self):
        console = CapturingConsole()
        console.echo("a")

        logs = console.get_logs()
        logs.append({"msg": "mutated"})

        # Mutating the returned list must not affect the buffer.
        assert len(console.buffer) == 1

    def test_get_logs_filters_by_max_level(self):
        console = CapturingConsole()
        console.echo("low", level=0)
        console.echo("mid", level=1)
        console.echo("high", level=2)

        logs = console.get_logs(max_level=1)

        assert [entry["msg"] for entry in logs] == ["low", "mid"]


class TestGetConsole:
    """get_console picks the console implementation by environment."""

    def test_returns_testing_console_under_pytest(self):
        # PYTEST_VERSION is set while the suite runs.
        assert isinstance(get_console(), InMemoryConsole)

    def test_returns_printing_console_without_pytest(self, monkeypatch):
        monkeypatch.delenv("PYTEST_VERSION", raising=False)

        assert isinstance(get_console(), PrintingConsole)


class TestConsoleRegistry:
    """set_console swaps the global console and returns the previous one."""

    def test_set_console_returns_old_and_installs_new(self, restore_console):
        new = InMemoryConsole()

        old = set_console(new)

        assert get_current_console() is new
        assert old is not new

    def test_echo_uses_current_console(self, restore_console):
        new = InMemoryConsole()
        set_console(new)

        echo("routed", fg="green")

        assert new.buffer == ["routed"]


class TestVerbosity:
    """set_verbosity / get_verbosity manage the global verbosity level."""

    def test_set_verbosity_returns_old_and_updates(self, restore_verbosity):
        set_verbosity(1)

        old = set_verbosity(3)

        assert old == 1
        assert get_verbosity() == 3

    def test_verbosity_context_restores_previous_level(self, restore_verbosity):
        set_verbosity(1)

        with VerbosityContext(2) as level:
            assert level == 2
            assert get_verbosity() == 2

        assert get_verbosity() == 1

    def test_verbosity_context_restores_on_exception(self, restore_verbosity):
        set_verbosity(1)

        with pytest.raises(BoomError):  # ruff:ignore[multiple-with-statements]
            with VerbosityContext(3):
                assert get_verbosity() == 3
                raise BoomError

        assert get_verbosity() == 1


class TestCaptureLogs:
    """CaptureLogs swaps in a CapturingConsole and restores afterwards."""

    def test_enter_installs_capturing_console(self, restore_console):
        original = get_current_console()

        with CaptureLogs() as captured:
            assert isinstance(captured, CapturingConsole)
            assert get_current_console() is captured

        assert get_current_console() is original

    def test_uses_explicit_verbosity(self, restore_console):
        with CaptureLogs(verbosity=3) as captured:
            assert captured.verbosity == 3

    def test_defaults_to_global_verbosity(self, restore_console, restore_verbosity):
        set_verbosity(2)

        with CaptureLogs() as captured:
            assert captured.verbosity == 2

    def test_restores_console_on_exception(self, restore_console):
        original = get_current_console()

        with pytest.raises(BoomError):  # ruff:ignore[multiple-with-statements]
            with CaptureLogs():
                raise BoomError

        assert get_current_console() is original


class TestLog:
    """log() formats messages and respects verbosity / console type."""

    def test_level_zero_uses_arrow_prefix(self, restore_console):
        console = InMemoryConsole()
        set_console(console)

        log("hello", level=0)

        assert console.buffer == ["> hello"]

    def test_positive_level_adds_dashes(self, restore_console, restore_verbosity):
        console = InMemoryConsole()
        set_console(console)
        set_verbosity(3)

        log("deep", level=2)

        assert console.buffer == ["--> deep"]

    def test_suppressed_when_level_above_verbosity(
        self, restore_console, restore_verbosity
    ):
        console = InMemoryConsole()
        set_console(console)
        set_verbosity(1)

        log("verbose-only", level=2)

        assert console.buffer == []

    def test_capturing_console_always_records(self, restore_console, restore_verbosity):
        # A CapturingConsole does its own filtering, so log() must not pre-filter.
        console = CapturingConsole(verbosity=3)
        set_console(console)
        set_verbosity(0)

        log("captured", level=2)

        assert console.buffer == [{"msg": "--> captured", "fg": "green", "level": 2}]

    def test_routes_to_active_stream(self, restore_console, monkeypatch):
        console = InMemoryConsole()
        set_console(console)

        recorded: list[dict] = []

        class StubStream:
            def write(self, formatted, level, fg):
                recorded.append({"formatted": formatted, "level": level, "fg": fg})

        stub = StubStream()
        monkeypatch.setattr(
            "hop3.server.streaming.get_current_stream",
            lambda: stub,
        )

        log("streamed", level=1, fg="red")

        assert recorded == [{"formatted": "-> streamed", "level": 1, "fg": "red"}]


class TestPanic:
    """panic() logs in red and exits with status 1."""

    def test_panic_exits_with_status_one(self, restore_console):
        console = InMemoryConsole()
        set_console(console)

        with pytest.raises(SystemExit) as exc_info:
            panic("fatal")

        assert exc_info.value.code == 1
        assert console.buffer == ["> fatal"]


class TestAbort:
    """Abort stores its details and logs the message when constructed."""

    def test_stores_fields(self, restore_console):
        set_console(InMemoryConsole())

        err = Abort("boom", status=7, explanation="why")

        assert err.msg == "boom"
        assert err.status == 7
        assert err.explanation == "why"

    def test_defaults(self, restore_console):
        set_console(InMemoryConsole())

        err = Abort()

        assert err.msg == "unknown error"
        assert err.status == 1
        assert err.explanation == ""

    def test_empty_message_falls_back_to_unknown_error(self, restore_console):
        set_console(InMemoryConsole())

        err = Abort("")

        assert err.msg == "unknown error"

    def test_logs_message_on_construction(self, restore_console):
        console = InMemoryConsole()
        set_console(console)

        Abort("kaput")

        assert console.buffer == ["> kaput"]

    def test_is_an_exception(self, restore_console):
        set_console(InMemoryConsole())
        err = Abort("raise me")

        with pytest.raises(Abort):
            raise err
