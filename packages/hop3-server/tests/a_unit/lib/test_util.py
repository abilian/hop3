# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for the pure / hermetically-testable helpers in hop3.lib.util.

Command-execution exceptions (CommandError & friends), run_command and
try_commands are covered in test_command.py; this file covers the remaining
public helpers: sanitize_app_name, the port helpers, check_binaries,
command_output, multi_tail and robust_rmtree.
"""

from __future__ import annotations

import os
import socket
import stat

import pytest

from hop3.lib.util import (
    check_binaries,
    command_output,
    get_free_port,
    is_port_free,
    multi_tail,
    robust_rmtree,
    sanitize_app_name,
)


class TestSanitizeAppName:
    """Tests for sanitize_app_name."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("my-app", "my-app"),
            ("app.name_1-2", "app.name_1-2"),  # all allowed punctuation kept
            ("MixedCASE123", "MixedCASE123"),  # alphanumerics preserved verbatim
        ],
    )
    def test_keeps_valid_characters(self, raw, expected):
        """Alphanumerics plus '.', '_', '-' are preserved as-is."""
        assert sanitize_app_name(raw) == expected

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("my app!@#name", "myappname"),  # spaces and symbols dropped
            ("a/b c", "abc"),  # slashes and spaces dropped
            ("foo$bar%baz", "foobarbaz"),
        ],
    )
    def test_strips_invalid_characters(self, raw, expected):
        """Characters outside the allowlist are removed entirely."""
        assert sanitize_app_name(raw) == expected

    def test_removes_leading_slashes(self):
        """Leading slashes do not appear in the sanitized name."""
        assert sanitize_app_name("/my-app") == "my-app"
        assert sanitize_app_name("///nested-path") == "nested-path"

    def test_empty_string_returns_empty(self):
        """An empty input yields an empty result."""
        assert sanitize_app_name("") == ""

    def test_only_invalid_characters_returns_empty(self):
        """A name made of only disallowed characters collapses to empty."""
        assert sanitize_app_name("/// $$$ ///") == ""


class TestIsPortFree:
    """Tests for is_port_free."""

    def test_unbound_port_is_free(self):
        """A port nobody is listening on reports free."""
        # get_free_port hands back an OS-allocated, currently-unused port.
        port = get_free_port("127.0.0.1")

        assert is_port_free(port) is True

    def test_bound_port_is_not_free(self):
        """A port held by an open socket reports not free."""
        held = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        held.bind(("127.0.0.1", 0))
        port = held.getsockname()[1]
        try:
            assert is_port_free(port) is False
        finally:
            held.close()


class TestGetFreePort:
    """Tests for get_free_port."""

    def test_returns_int_in_valid_range(self):
        """get_free_port returns a usable TCP port number."""
        port = get_free_port("127.0.0.1")

        assert isinstance(port, int)
        assert 1 <= port <= 65535

    def test_returned_port_is_actually_free(self):
        """The port returned can immediately be reported free."""
        port = get_free_port("127.0.0.1")

        assert is_port_free(port) is True


class TestCheckBinaries:
    """Tests for check_binaries."""

    def test_all_present_returns_true(self):
        """All binaries found on PATH yields True."""
        # 'sh' and 'ls' exist on every POSIX host the suite runs on.
        assert check_binaries(["sh", "ls"]) is True

    def test_missing_binary_returns_false(self):
        """A single missing binary makes the whole check fail."""
        assert check_binaries(["sh", "definitely_not_a_real_binary_xyz_123"]) is False

    def test_empty_list_returns_true(self):
        """With nothing to check, the requirement is vacuously satisfied."""
        assert check_binaries([]) is True


class TestCommandOutput:
    """Tests for command_output."""

    def test_string_command_is_split_and_run(self):
        """A string command is shlex-split and its stdout returned."""
        assert command_output("echo hello world") == "hello world\n"

    def test_list_command_is_run_directly(self):
        """A list command is executed without re-parsing."""
        assert command_output(["echo", "spaced arg"]) == "spaced arg\n"

    def test_quoted_string_is_parsed_safely(self):
        """shlex.split keeps quoted segments together as one argument."""
        assert command_output('echo "one arg"') == "one arg\n"

    def test_missing_command_returns_empty_string(self):
        """A command not found on PATH yields an empty string, not an error."""
        assert command_output("nonexistent_command_xyz_123") == ""

    def test_failing_command_returns_empty_string(self):
        """A non-zero exit code yields an empty string."""
        assert command_output("false") == ""

    def test_captures_stderr_via_redirect(self):
        """stderr is merged into the captured output (STDOUT redirect)."""
        result = command_output(["sh", "-c", "echo to_stderr >&2"])

        assert result == "to_stderr\n"


class TestMultiTail:
    """Tests for multi_tail (the initial, finite portion of the stream)."""

    def test_yields_recent_lines_prefixed_with_stem(self, tmp_path):
        """Initial output is the last catch_up lines, prefixed by file stem."""
        log = tmp_path / "app.log"
        log.write_text("line1\nline2\nline3\n")

        stream = multi_tail([str(log)], catch_up=2)
        # Only consume the finite initial_tail portion; follow() loops forever.
        first = next(stream)
        second = next(stream)

        assert first == "app | line2\n"
        assert second == "app | line3\n"

    def test_stem_column_padded_to_longest(self, tmp_path):
        """The stem column is left-justified to the longest stem across files."""
        short = tmp_path / "aa.log"
        short.write_text("x\n")
        long = tmp_path / "longname.log"
        long.write_text("y\n")

        stream = multi_tail([str(short), str(long)], catch_up=1)
        first = next(stream)
        second = next(stream)

        # "aa" padded to width of "longname" (8 chars).
        assert first == "aa       | x\n"
        assert second == "longname | y\n"

    def test_catch_up_limits_initial_lines(self, tmp_path):
        """Only the last catch_up lines per file are emitted initially."""
        log = tmp_path / "many.log"
        log.write_text("\n".join(f"l{i}" for i in range(10)) + "\n")

        stream = multi_tail([str(log)], catch_up=3)
        emitted = [next(stream) for _ in range(3)]

        assert emitted == ["many | l7\n", "many | l8\n", "many | l9\n"]


class TestRobustRmtree:
    """Tests for robust_rmtree."""

    def test_missing_path_is_noop(self, tmp_path):
        """Removing a non-existent path does nothing and does not raise."""
        target = tmp_path / "does_not_exist"

        robust_rmtree(target)  # Should not raise.

        assert not target.exists()

    def test_removes_plain_directory_tree(self, tmp_path):
        """A nested directory tree is fully removed."""
        tree = tmp_path / "tree"
        (tree / "sub").mkdir(parents=True)
        (tree / "sub" / "file.txt").write_text("data")

        robust_rmtree(tree)

        assert not tree.exists()

    def test_accepts_string_path(self, tmp_path):
        """A str path is coerced to Path and removed."""
        tree = tmp_path / "tree"
        tree.mkdir()
        (tree / "f.txt").write_text("x")

        robust_rmtree(str(tree))

        assert not tree.exists()

    def test_symlink_is_unlinked_target_preserved(self, tmp_path):
        """A symlink to a directory is unlinked; its target is left intact."""
        target = tmp_path / "real_dir"
        target.mkdir()
        (target / "keep.txt").write_text("keep me")
        link = tmp_path / "link"
        link.symlink_to(target, target_is_directory=True)

        robust_rmtree(link)

        assert not link.exists()  # follows to target; symlink itself is gone
        assert not link.is_symlink()
        assert target.exists()
        assert (target / "keep.txt").read_text() == "keep me"

    def test_removes_readonly_file(self, tmp_path):
        """Read-only files are chmod'd and removed via the error handler."""
        directory = tmp_path / "ro"
        directory.mkdir()
        readonly = directory / "readonly.txt"
        readonly.write_text("locked")
        os.chmod(readonly, stat.S_IRUSR)

        robust_rmtree(directory)

        assert not directory.exists()
