# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for RichPrinter class."""

from __future__ import annotations

import base64
import json

import pytest
from hop3_cli.ui.rich_printer import RichPrinter


def test_rich_printer_creation():
    """Test RichPrinter instantiation with different flags."""
    # Default printer
    printer = RichPrinter()
    assert printer.verbose is False
    assert printer.quiet is False
    assert printer.json_output is False

    # With flags
    printer = RichPrinter(verbose=True, quiet=False, json_output=True)
    assert printer.verbose is True
    assert printer.quiet is False
    assert printer.json_output is True


def test_rich_printer_print_text_normal(capsys):
    """Test printing text in normal mode."""
    printer = RichPrinter()

    printer.print([{"t": "text", "text": "Hello, world!"}])
    output = capsys.readouterr().out
    assert "Hello, world!" in output


def test_rich_printer_print_text_preserves_square_brackets(capsys):
    """
    Plain text with square brackets must print literally (not as Rich markup).

    Help output uses literal brackets the user must see: the ``[top]`` /
    ``[addon]`` markers in ``hop3 help --all`` and ``[options]`` / ``[aliases]``
    / ``[local]`` in command help. Rich's markup parser would otherwise treat
    these as style tags and strip them.
    """
    printer = RichPrinter()

    printer.print([
        {
            "t": "text",
            "text": (
                "  addon attach    [addon]   Attach a service.\n"
                "Add it under the [aliases] section.\n"
                "  3. .hop3-local.toml [local].context"
            ),
        }
    ])
    output = capsys.readouterr().out
    assert "[addon]" in output
    assert "[aliases]" in output
    assert "[local]" in output


def test_rich_printer_does_not_wrap_long_single_line_value(capsys):
    """
    A long single-line value must not be word-wrapped.

    `hop3 auth get-token` prints a bare JWT for `TOKEN=$(...)`. When stdout is
    piped (not a TTY) Rich defaults to 80 cols and would word-wrap the token,
    injecting hard newlines that corrupt it. soft_wrap keeps it on one line.
    """
    token = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiJ0ZXN0LWRpYWdub3N0aWMtdXNlciIsInNjb3BlcyI6WyJhdXRoZW50aWNhdGVkIl0."
        "qdGkiOiJfa0pLZEFERWtvcDU5SDF5Uk1xVi1nSQ"
    )
    printer = RichPrinter()

    printer.print([{"t": "text", "text": token}])
    output = capsys.readouterr().out
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    # Mirrors the script-side parser: a single line that IS the JWT.
    assert token in lines, f"token was wrapped across lines: {output!r}"


def test_summary_and_error_lines_are_not_wrapped(capsys):
    """
    The two items a quiet client prints stay one line each when piped.

    `hop3 system status --quiet` answers with one summary line for scripts;
    Rich wrapped it at 80 columns on stderr, as it once did the JWT on stdout.
    """
    line = "DEGRADED: redis unreachable — Error 111 connecting to 127.0.0.1:6379. " * 2
    printer = RichPrinter(quiet=True)
    printer.print([{"t": "summary", "text": line}, {"t": "error", "text": line}])
    err = capsys.readouterr().err

    lines = [ln for ln in err.splitlines() if ln.strip()]
    assert len(lines) == 2, lines


def test_rich_printer_print_blob_writes_raw_bytes_to_stdout(capsysbinary):
    """
    A blob item (base64) is decoded and written verbatim to stdout.buffer.

    Used by `addon <type> export` so a dump can be redirected to a file.
    """
    printer = RichPrinter()
    printer.print([
        {"t": "blob", "data": base64.b64encode(b"DUMP-BYTES\x00\x01").decode()}
    ])

    assert capsysbinary.readouterr().out == b"DUMP-BYTES\x00\x01"


def test_rich_printer_print_text_quiet(capsys):
    """Test that quiet mode suppresses text output."""
    printer = RichPrinter(quiet=True)

    printer.print([{"t": "text", "text": "Hello, world!"}])
    output = capsys.readouterr().out
    assert output == ""


def test_rich_printer_print_text_json(capsys):
    """Test that JSON mode buffers text for later output."""
    printer = RichPrinter(json_output=True)

    printer.print([{"t": "text", "text": "Hello, world!"}])
    out = capsys.readouterr().out

    # Should not print immediately
    output = out
    assert output == ""

    # Should buffer for later
    printer.flush_json()
    output = capsys.readouterr().out
    data = json.loads(output)
    assert len(data) == 1
    assert data[0]["t"] == "text"
    assert data[0]["text"] == "Hello, world!"


def test_rich_printer_print_error(capsys):
    """Test printing errors to stderr."""
    printer = RichPrinter()

    printer.print([{"t": "error", "text": "Something went wrong"}])
    err = capsys.readouterr().err

    output = err
    assert "Something went wrong" in output


def test_rich_printer_print_error_quiet(capsys):
    """Test that errors are NOT suppressed in quiet mode."""
    printer = RichPrinter(quiet=True)

    printer.print([{"t": "error", "text": "Something went wrong"}])
    err = capsys.readouterr().err

    output = err
    assert "Something went wrong" in output


def test_rich_printer_print_success(capsys):
    """Test printing success messages with checkmark."""
    printer = RichPrinter()

    printer.print([{"t": "success", "text": "Deployment complete"}])
    output = capsys.readouterr().out
    assert "Deployment complete" in output


def test_rich_printer_print_warning(capsys):
    """Test printing warning messages — routed to stderr per ADR 036 D19."""
    printer = RichPrinter()

    printer.print([{"t": "warning", "text": "This is deprecated"}])
    out, err = capsys.readouterr()

    assert "This is deprecated" in err
    assert "This is deprecated" not in out


def test_rich_printer_print_table(capsys):
    """Test printing tables using Rich."""
    printer = RichPrinter()

    table_data = {
        "t": "table",
        "headers": ["Name", "Status", "Port"],
        "rows": [
            ["my-app", "RUNNING", "8000"],
            ["test-app", "STOPPED", "8001"],
        ],
    }

    printer.print([table_data])
    output = capsys.readouterr().out
    # Rich table should contain headers and data
    assert "Name" in output
    assert "Status" in output
    assert "Port" in output
    assert "my-app" in output
    assert "RUNNING" in output
    assert "8000" in output


def test_rich_printer_print_table_json(capsys):
    """Test that JSON mode preserves table structure."""
    printer = RichPrinter(json_output=True)

    table_data = {
        "t": "table",
        "headers": ["Name", "Status"],
        "rows": [["my-app", "RUNNING"]],
    }

    printer.print([table_data])
    printer.flush_json()
    output = capsys.readouterr().out
    data = json.loads(output)
    assert len(data) == 1
    assert data[0]["t"] == "table"
    assert data[0]["headers"] == ["Name", "Status"]
    assert data[0]["rows"] == [["my-app", "RUNNING"]]


def test_rich_printer_multiple_messages(capsys):
    """Test printing multiple messages at once."""
    printer = RichPrinter()

    messages = [
        {"t": "text", "text": "Starting deployment..."},
        {"t": "success", "text": "Build successful"},
        {"t": "text", "text": "Deploy complete"},
    ]

    printer.print(messages)
    output = capsys.readouterr().out
    assert "Starting deployment..." in output
    assert "Build successful" in output
    assert "Deploy complete" in output


def test_rich_printer_flush_json_empty(capsys):
    """Test flushing JSON with empty buffer."""
    printer = RichPrinter(json_output=True)

    printer.flush_json()
    output = capsys.readouterr().out
    assert output == "[]\n"


def test_rich_printer_flush_json_multiple(capsys):
    """Test flushing JSON with multiple buffered messages."""
    printer = RichPrinter(json_output=True)

    printer.print([{"t": "text", "text": "Message 1"}])
    printer.print([{"t": "text", "text": "Message 2"}])
    printer.print([{"t": "success", "text": "Done"}])

    printer.flush_json()
    output = capsys.readouterr().out
    data = json.loads(output)
    assert len(data) == 3
    assert data[0]["text"] == "Message 1"
    assert data[1]["text"] == "Message 2"
    assert data[2]["text"] == "Done"


def test_rich_printer_table_with_none_values(capsys):
    """Test that table handles None values gracefully."""
    printer = RichPrinter()

    table_data = {
        "t": "table",
        "headers": ["Name", "Value"],
        "rows": [
            ["key1", None],
            ["key2", "value2"],
        ],
    }

    printer.print([table_data])
    output = capsys.readouterr().out
    # Should handle None without crashing
    assert "key1" in output
    assert "key2" in output
    assert "value2" in output


def test_rich_printer_unknown_message_type(capsys):
    """An item type this client does not know still shows its text."""
    printer = RichPrinter()

    printer.print([{"t": "from-a-newer-server", "text": "something"}])

    assert "something" in capsys.readouterr().out


def test_rich_printer_unknown_type_without_text_is_shown_not_dropped(capsys):
    """It printed an empty line: the item's content vanished."""
    printer = RichPrinter(quiet=True)

    printer.print([{"t": "gauge", "value": 42, "label": "[disk]"}])

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Unknown output item" in captured.err
    assert '"t": "gauge"' in captured.err
    assert '"label": "[disk]"' in captured.err  # literal, not Rich markup


def test_rich_printer_empty_message_list(capsys):
    """Test printing empty message list."""
    printer = RichPrinter()

    printer.print([])

    assert capsys.readouterr().out == ""


def test_rich_printer_verbose_flag():
    """Test that verbose flag is accessible."""
    printer = RichPrinter(verbose=True)
    assert printer.verbose is True

    # Future: verbose mode may add extra output
    # For now, just verify the flag is stored correctly


def test_rich_printer_immutability():
    """Test that RichPrinter is immutable (frozen dataclass)."""
    printer = RichPrinter(quiet=False)

    try:
        printer.quiet = True  # type: ignore
        msg = "Should have raised AttributeError"
        raise AssertionError(msg)
    except AttributeError:
        # Expected - frozen dataclass
        pass


def test_rich_printer_json_output_format(capsys):
    """Test that JSON output is valid and properly formatted."""
    printer = RichPrinter(json_output=True)

    printer.print([{"t": "text", "text": "Test message"}])

    printer.flush_json()
    output = capsys.readouterr().out

    # Should be valid JSON
    data = json.loads(output)
    assert isinstance(data, list)

    # Should end with newline for shell scripting
    assert output.endswith("\n")


# ---- Summary rendering (ADR 036 D19c) ----


def test_summary_routes_to_stderr(capsys):
    """Summary lines go to stderr so stdout pipelines stay clean."""
    printer = RichPrinter()
    printer.set_scope(context="prod", app="myapp")

    printer.print([{"t": "summary", "text": "set FOO=bar; restarted web."}])
    out, err = capsys.readouterr()

    assert out == ""
    assert "set FOO=bar; restarted web." in err


def test_summary_includes_context_and_app_prefix(capsys):
    """The [context / app] prefix is built from the scope set by main."""
    printer = RichPrinter()
    printer.set_scope(context="prod", app="myapp")

    printer.print([{"t": "summary", "text": "deployed rev abc123."}])
    out, err = capsys.readouterr()

    out = err
    assert "[prod / myapp]" in out
    assert "deployed rev abc123." in out


def test_summary_with_only_context(capsys):
    """No app set -> prefix shows only the context."""
    printer = RichPrinter()
    printer.set_scope(context="prod", app=None)

    printer.print([{"t": "summary", "text": "context updated."}])
    out, err = capsys.readouterr()

    out = err
    assert "[prod]" in out
    assert " / " not in out


def test_summary_without_scope_omits_prefix(capsys):
    """No context and no app -> just the text, no empty brackets."""
    printer = RichPrinter()  # no set_scope call

    printer.print([{"t": "summary", "text": "alias added."}])
    out, err = capsys.readouterr()

    out = err
    assert "alias added." in out
    assert "[" not in out


def test_summary_in_json_mode_buffers(capsys):
    """JSON mode should buffer summary items like everything else."""
    printer = RichPrinter(json_output=True)
    printer.set_scope(context="prod", app="myapp")

    printer.print([{"t": "summary", "text": "deployed rev abc."}])

    printer.flush_json()
    out = capsys.readouterr().out

    data = json.loads(out)
    assert data == [{"t": "summary", "text": "deployed rev abc."}]


def test_summary_survives_quiet_mode(capsys):
    """Summary is the one signal scripts can scrape; --quiet must not eat it."""
    printer = RichPrinter(quiet=True)
    printer.set_scope(context="prod", app="myapp")

    printer.print([{"t": "summary", "text": "set FOO=bar."}])
    err = capsys.readouterr().err

    assert "set FOO=bar." in err


def test_rich_printer_table_empty_rows(capsys):
    """Test table with headers but no rows."""
    printer = RichPrinter()

    table_data = {
        "t": "table",
        "headers": ["Name", "Status"],
        "rows": [],
    }

    printer.print([table_data])
    output = capsys.readouterr().out
    # Should show headers even with no rows
    assert "Name" in output
    assert "Status" in output


def test_print_error_with_bracketed_text_does_not_crash(capsys):
    """
    Server-supplied error text routinely contains brackets that are NOT Rich
    markup — MSBuild appends ``[/path/app.csproj]`` to every diagnostic. Such a
    closing-bracket sequence used to make Rich raise a MarkupError that masked
    the real failure. The text must print literally instead.
    """
    printer = RichPrinter()

    msbuild_line = (
        "Program.cs(10,5): error CS1002: ; expected "
        "[/home/hop3/apps/myapp/src/myapp.csproj]"
    )

    # Must not raise rich.errors.MarkupError.
    printer.print([{"t": "error", "text": msbuild_line}])
    err = capsys.readouterr().err

    output = err
    assert "CS1002" in output
    assert "myapp.csproj" in output  # the bracketed path survives, not stripped


def test_print_success_with_bracketed_text_does_not_crash(capsys):
    """A success line carrying bracketed dynamic text must not trip Rich markup."""
    printer = RichPrinter()

    printer.print([{"t": "success", "text": "built [/tmp/out] ok"}])
    out = capsys.readouterr().out

    assert "/tmp/out" in out


def _render_hint(capsys, item, *, context=None, app):
    """Render a single `hint` item with the given typed selectors; return stdout."""
    printer = RichPrinter()
    printer.set_suggestion_selectors(context=context, app=app)
    printer.print([item])
    out = capsys.readouterr().out
    return out


def test_hint_echoes_typed_context(capsys):
    """
    A follow-up suggestion carries the --context the user typed, so a
    copy-paste stays on the same server (it never reaches the server itself).
    """
    item = {"t": "hint", "command": "deploy", "message": "Run {cmd} to apply."}
    out = _render_hint(capsys, item, context="prod", app=None)
    assert "hop3 deploy --context prod" in out
    assert "{cmd}" not in out  # placeholder was substituted


def test_hint_echoes_typed_app(capsys):
    item = {"t": "hint", "command": "deploy", "message": "Run {cmd}."}
    out = _render_hint(capsys, item, context="prod", app="myapp")
    assert "hop3 deploy --context prod --app myapp" in out


def test_hint_omits_implicit_selectors(capsys):
    """
    No --app/--context typed (implicit resolution) → suggestion omits them and
    resolves the same way on the next run.
    """
    item = {"t": "hint", "command": "deploy", "message": "Run {cmd}."}
    out = _render_hint(capsys, item, context=None, app=None)
    assert "hop3 deploy" in out
    assert "--context" not in out
    assert "--app" not in out


def test_hint_keeps_the_app_it_names(capsys):
    """
    A restore into another app points at that app's status: the --app the
    user typed must not be appended beside it.
    """
    item = {
        "t": "hint",
        "command": "app status --app restored",
        "message": "Run {cmd}.",
    }
    out = _render_hint(capsys, item, context="prod", app="original")
    assert "hop3 app status --app restored --context prod" in out
    assert "original" not in out


@pytest.mark.parametrize(
    ("command", "dropped"),
    [("logs -a restored", "original"), ("status --context staging", "prod")],
)
def test_hint_keeps_a_selector_it_names_in_either_spelling(capsys, command, dropped):
    """A hint that names `-a` or `--context` gets no second one appended."""
    item = {"t": "hint", "command": command, "message": "Run {cmd}."}
    out = _render_hint(capsys, item, context="prod", app="original")
    assert f"hop3 {command}" in out
    assert dropped not in out
