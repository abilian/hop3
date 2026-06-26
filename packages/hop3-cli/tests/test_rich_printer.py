# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for RichPrinter class."""

from __future__ import annotations

import base64
import json
import sys
from io import BytesIO, StringIO
from unittest.mock import patch

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


def test_rich_printer_print_text_normal():
    """Test printing text in normal mode."""
    printer = RichPrinter()

    stdout_capture = StringIO()
    with patch.object(sys, "stdout", stdout_capture):
        printer.print([{"t": "text", "text": "Hello, world!"}])

    output = stdout_capture.getvalue()
    assert "Hello, world!" in output


def test_rich_printer_print_text_preserves_square_brackets():
    """Plain text with square brackets must print literally (not as Rich markup).

    Help output uses literal brackets the user must see: the ``[top]`` /
    ``[addon]`` markers in ``hop help --all`` and ``[options]`` / ``[aliases]``
    / ``[local]`` in command help. Rich's markup parser would otherwise treat
    these as style tags and strip them.
    """
    printer = RichPrinter()

    stdout_capture = StringIO()
    with patch.object(sys, "stdout", stdout_capture):
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

    output = stdout_capture.getvalue()
    assert "[addon]" in output
    assert "[aliases]" in output
    assert "[local]" in output


def test_rich_printer_print_blob_writes_raw_bytes_to_stdout():
    """A blob item (base64) is decoded and written verbatim to stdout.buffer.

    Used by `addon <type> export` so a dump can be redirected to a file.
    """
    printer = RichPrinter()
    raw_buffer = BytesIO()

    class _FakeStdout:
        buffer = raw_buffer

        def flush(self):
            pass

    with patch.object(sys, "stdout", _FakeStdout()):
        printer.print([
            {"t": "blob", "data": base64.b64encode(b"DUMP-BYTES\x00\x01").decode()}
        ])

    assert raw_buffer.getvalue() == b"DUMP-BYTES\x00\x01"


def test_rich_printer_print_text_quiet():
    """Test that quiet mode suppresses text output."""
    printer = RichPrinter(quiet=True)

    stdout_capture = StringIO()
    with patch.object(sys, "stdout", stdout_capture):
        printer.print([{"t": "text", "text": "Hello, world!"}])

    output = stdout_capture.getvalue()
    assert output == ""


def test_rich_printer_print_text_json():
    """Test that JSON mode buffers text for later output."""
    printer = RichPrinter(json_output=True)

    stdout_capture = StringIO()
    with patch.object(sys, "stdout", stdout_capture):
        printer.print([{"t": "text", "text": "Hello, world!"}])

    # Should not print immediately
    output = stdout_capture.getvalue()
    assert output == ""

    # Should buffer for later
    stdout_capture = StringIO()
    with patch.object(sys, "stdout", stdout_capture):
        printer.flush_json()

    output = stdout_capture.getvalue()
    data = json.loads(output)
    assert len(data) == 1
    assert data[0]["t"] == "text"
    assert data[0]["text"] == "Hello, world!"


def test_rich_printer_print_error():
    """Test printing errors to stderr."""
    printer = RichPrinter()

    stderr_capture = StringIO()
    with patch.object(sys, "stderr", stderr_capture):
        printer.print([{"t": "error", "text": "Something went wrong"}])

    output = stderr_capture.getvalue()
    assert "Something went wrong" in output


def test_rich_printer_print_error_quiet():
    """Test that errors are NOT suppressed in quiet mode."""
    printer = RichPrinter(quiet=True)

    stderr_capture = StringIO()
    with patch.object(sys, "stderr", stderr_capture):
        printer.print([{"t": "error", "text": "Something went wrong"}])

    output = stderr_capture.getvalue()
    assert "Something went wrong" in output


def test_rich_printer_print_success():
    """Test printing success messages with checkmark."""
    printer = RichPrinter()

    stdout_capture = StringIO()
    with patch.object(sys, "stdout", stdout_capture):
        printer.print([{"t": "success", "text": "Deployment complete"}])

    output = stdout_capture.getvalue()
    assert "Deployment complete" in output


def test_rich_printer_print_warning():
    """Test printing warning messages — routed to stderr per ADR 036 D19."""
    printer = RichPrinter()

    stdout_capture = StringIO()
    stderr_capture = StringIO()
    with (
        patch.object(sys, "stdout", stdout_capture),
        patch.object(sys, "stderr", stderr_capture),
    ):
        printer.print([{"t": "warning", "text": "This is deprecated"}])

    assert "This is deprecated" in stderr_capture.getvalue()
    assert "This is deprecated" not in stdout_capture.getvalue()


def test_rich_printer_print_table():
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

    stdout_capture = StringIO()
    with patch.object(sys, "stdout", stdout_capture):
        printer.print([table_data])

    output = stdout_capture.getvalue()
    # Rich table should contain headers and data
    assert "Name" in output
    assert "Status" in output
    assert "Port" in output
    assert "my-app" in output
    assert "RUNNING" in output
    assert "8000" in output


def test_rich_printer_print_table_json():
    """Test that JSON mode preserves table structure."""
    printer = RichPrinter(json_output=True)

    table_data = {
        "t": "table",
        "headers": ["Name", "Status"],
        "rows": [["my-app", "RUNNING"]],
    }

    stdout_capture = StringIO()
    with patch.object(sys, "stdout", stdout_capture):
        printer.print([table_data])
        printer.flush_json()

    output = stdout_capture.getvalue()
    data = json.loads(output)
    assert len(data) == 1
    assert data[0]["t"] == "table"
    assert data[0]["headers"] == ["Name", "Status"]
    assert data[0]["rows"] == [["my-app", "RUNNING"]]


def test_rich_printer_multiple_messages():
    """Test printing multiple messages at once."""
    printer = RichPrinter()

    messages = [
        {"t": "text", "text": "Starting deployment..."},
        {"t": "success", "text": "Build successful"},
        {"t": "text", "text": "Deploy complete"},
    ]

    stdout_capture = StringIO()
    with patch.object(sys, "stdout", stdout_capture):
        printer.print(messages)

    output = stdout_capture.getvalue()
    assert "Starting deployment..." in output
    assert "Build successful" in output
    assert "Deploy complete" in output


def test_rich_printer_flush_json_empty():
    """Test flushing JSON with empty buffer."""
    printer = RichPrinter(json_output=True)

    stdout_capture = StringIO()
    with patch.object(sys, "stdout", stdout_capture):
        printer.flush_json()

    output = stdout_capture.getvalue()
    assert output == "[]\n"


def test_rich_printer_flush_json_multiple():
    """Test flushing JSON with multiple buffered messages."""
    printer = RichPrinter(json_output=True)

    printer.print([{"t": "text", "text": "Message 1"}])
    printer.print([{"t": "text", "text": "Message 2"}])
    printer.print([{"t": "success", "text": "Done"}])

    stdout_capture = StringIO()
    with patch.object(sys, "stdout", stdout_capture):
        printer.flush_json()

    output = stdout_capture.getvalue()
    data = json.loads(output)
    assert len(data) == 3
    assert data[0]["text"] == "Message 1"
    assert data[1]["text"] == "Message 2"
    assert data[2]["text"] == "Done"


def test_rich_printer_table_with_none_values():
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

    stdout_capture = StringIO()
    with patch.object(sys, "stdout", stdout_capture):
        printer.print([table_data])

    output = stdout_capture.getvalue()
    # Should handle None without crashing
    assert "key1" in output
    assert "key2" in output
    assert "value2" in output


def test_rich_printer_unknown_message_type():
    """Test handling of unknown message types."""
    printer = RichPrinter()

    stdout_capture = StringIO()
    with patch.object(sys, "stdout", stdout_capture):
        # Should not crash on unknown type
        printer.print([{"t": "unknown", "data": "something"}])

    # Should produce some output or handle gracefully
    stdout_capture.getvalue()
    # Unknown types might be printed as-is or ignored
    # Implementation-specific behavior


def test_rich_printer_empty_message_list():
    """Test printing empty message list."""
    printer = RichPrinter()

    stdout_capture = StringIO()
    with patch.object(sys, "stdout", stdout_capture):
        printer.print([])

    output = stdout_capture.getvalue()
    assert output == ""


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


def test_rich_printer_json_output_format():
    """Test that JSON output is valid and properly formatted."""
    printer = RichPrinter(json_output=True)

    printer.print([{"t": "text", "text": "Test message"}])

    stdout_capture = StringIO()
    with patch.object(sys, "stdout", stdout_capture):
        printer.flush_json()

    output = stdout_capture.getvalue()

    # Should be valid JSON
    data = json.loads(output)
    assert isinstance(data, list)

    # Should end with newline for shell scripting
    assert output.endswith("\n")


# ---- Summary rendering (ADR 036 D19c) ----


def test_summary_routes_to_stderr():
    """Summary lines go to stderr so stdout pipelines stay clean."""
    printer = RichPrinter()
    printer.set_scope(context="prod", app="myapp")

    stdout_capture = StringIO()
    stderr_capture = StringIO()
    with (
        patch.object(sys, "stdout", stdout_capture),
        patch.object(sys, "stderr", stderr_capture),
    ):
        printer.print([{"t": "summary", "text": "set FOO=bar; restarted web."}])

    assert stdout_capture.getvalue() == ""
    assert "set FOO=bar; restarted web." in stderr_capture.getvalue()


def test_summary_includes_context_and_app_prefix():
    """The [context / app] prefix is built from the scope set by main."""
    printer = RichPrinter()
    printer.set_scope(context="prod", app="myapp")

    stderr_capture = StringIO()
    with patch.object(sys, "stderr", stderr_capture):
        printer.print([{"t": "summary", "text": "deployed rev abc123."}])

    out = stderr_capture.getvalue()
    assert "[prod / myapp]" in out
    assert "deployed rev abc123." in out


def test_summary_with_only_context():
    """No app set -> prefix shows only the context."""
    printer = RichPrinter()
    printer.set_scope(context="prod", app=None)

    stderr_capture = StringIO()
    with patch.object(sys, "stderr", stderr_capture):
        printer.print([{"t": "summary", "text": "context updated."}])

    out = stderr_capture.getvalue()
    assert "[prod]" in out
    assert " / " not in out


def test_summary_without_scope_omits_prefix():
    """No context and no app -> just the text, no empty brackets."""
    printer = RichPrinter()  # no set_scope call

    stderr_capture = StringIO()
    with patch.object(sys, "stderr", stderr_capture):
        printer.print([{"t": "summary", "text": "alias added."}])

    out = stderr_capture.getvalue()
    assert "alias added." in out
    assert "[" not in out


def test_summary_in_json_mode_buffers():
    """JSON mode should buffer summary items like everything else."""
    printer = RichPrinter(json_output=True)
    printer.set_scope(context="prod", app="myapp")

    printer.print([{"t": "summary", "text": "deployed rev abc."}])

    stdout_capture = StringIO()
    with patch.object(sys, "stdout", stdout_capture):
        printer.flush_json()

    data = json.loads(stdout_capture.getvalue())
    assert data == [{"t": "summary", "text": "deployed rev abc."}]


def test_summary_survives_quiet_mode():
    """Summary is the one signal scripts can scrape; --quiet must not eat it."""
    printer = RichPrinter(quiet=True)
    printer.set_scope(context="prod", app="myapp")

    stderr_capture = StringIO()
    with patch.object(sys, "stderr", stderr_capture):
        printer.print([{"t": "summary", "text": "set FOO=bar."}])

    assert "set FOO=bar." in stderr_capture.getvalue()


def test_rich_printer_table_empty_rows():
    """Test table with headers but no rows."""
    printer = RichPrinter()

    table_data = {
        "t": "table",
        "headers": ["Name", "Status"],
        "rows": [],
    }

    stdout_capture = StringIO()
    with patch.object(sys, "stdout", stdout_capture):
        printer.print([table_data])

    output = stdout_capture.getvalue()
    # Should show headers even with no rows
    assert "Name" in output
    assert "Status" in output


def test_print_error_with_bracketed_text_does_not_crash():
    """Server-supplied error text routinely contains brackets that are NOT Rich
    markup — MSBuild appends ``[/path/app.csproj]`` to every diagnostic. Such a
    closing-bracket sequence used to make Rich raise a MarkupError that masked
    the real failure. The text must print literally instead.
    """
    printer = RichPrinter()

    msbuild_line = (
        "Program.cs(10,5): error CS1002: ; expected "
        "[/home/hop3/apps/myapp/src/myapp.csproj]"
    )

    stderr_capture = StringIO()
    with patch.object(sys, "stderr", stderr_capture):
        # Must not raise rich.errors.MarkupError.
        printer.print([{"t": "error", "text": msbuild_line}])

    output = stderr_capture.getvalue()
    assert "CS1002" in output
    assert "myapp.csproj" in output  # the bracketed path survives, not stripped


def test_print_success_with_bracketed_text_does_not_crash():
    """A success line carrying bracketed dynamic text must not trip Rich markup."""
    printer = RichPrinter()

    stdout_capture = StringIO()
    with patch.object(sys, "stdout", stdout_capture):
        printer.print([{"t": "success", "text": "built [/tmp/out] ok"}])

    assert "/tmp/out" in stdout_capture.getvalue()


def _render_hint(item, *, context=None, app):
    """Render a single `hint` item with the given typed selectors; return stdout."""
    printer = RichPrinter()
    printer.set_suggestion_selectors(context=context, app=app)
    stdout_capture = StringIO()
    with patch.object(sys, "stdout", stdout_capture):
        printer.print([item])
    return stdout_capture.getvalue()


def test_hint_echoes_typed_context():
    """A follow-up suggestion carries the --context the user typed, so a
    copy-paste stays on the same server (it never reaches the server itself)."""
    item = {"t": "hint", "command": "deploy", "message": "Run {cmd} to apply."}
    out = _render_hint(item, context="prod", app=None)
    assert "hop3 deploy --context prod" in out
    assert "{cmd}" not in out  # placeholder was substituted


def test_hint_echoes_typed_app():
    item = {"t": "hint", "command": "deploy", "message": "Run {cmd}."}
    out = _render_hint(item, context="prod", app="myapp")
    assert "hop3 deploy --context prod --app myapp" in out


def test_hint_omits_implicit_selectors():
    """No --app/--context typed (implicit resolution) → suggestion omits them and
    resolves the same way on the next run."""
    item = {"t": "hint", "command": "deploy", "message": "Run {cmd}."}
    out = _render_hint(item, context=None, app=None)
    assert "hop3 deploy" in out
    assert "--context" not in out
    assert "--app" not in out
