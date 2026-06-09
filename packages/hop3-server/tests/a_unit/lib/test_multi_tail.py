# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the MultiTail file-following utility."""

from __future__ import annotations

from pathlib import Path

import pytest

from hop3.lib.multi_tail import MultiTail


def make_file(directory: Path, name: str, content: str = "") -> Path:
    """Create a file with the given content and return its path."""
    path = directory / name
    path.write_text(content)
    return path


class TestPostInit:
    """Tests for MultiTail.__post_init__ (file/inode/handle setup)."""

    def test_records_paths_for_each_filename(self, tmp_path):
        f1 = make_file(tmp_path, "a.log", "line\n")
        f2 = make_file(tmp_path, "b.log", "line\n")

        mt = MultiTail(filenames=[str(f1), str(f2)])

        assert mt.paths == [Path(f1), Path(f2)]

    def test_records_inode_for_each_path(self, tmp_path):
        f1 = make_file(tmp_path, "a.log", "x\n")

        mt = MultiTail(filenames=[str(f1)])

        assert mt.inodes[Path(f1)] == Path(f1).stat().st_ino

    def test_opens_handle_for_each_path(self, tmp_path):
        f1 = make_file(tmp_path, "a.log", "x\n")

        mt = MultiTail(filenames=[str(f1)])

        handle = mt.handles[Path(f1)]
        assert not handle.closed
        handle.close()

    def test_handle_is_seeked_to_end(self, tmp_path):
        """The initial handle is positioned at EOF so 'follow' skips old content."""
        f1 = make_file(tmp_path, "a.log", "existing content\n")

        mt = MultiTail(filenames=[str(f1)])

        handle = mt.handles[Path(f1)]
        assert handle.tell() == len("existing content\n")
        handle.close()

    def test_accepts_path_objects_as_filenames(self, tmp_path):
        f1 = make_file(tmp_path, "a.log", "x\n")

        mt = MultiTail(filenames=[f1])

        assert mt.paths == [f1]
        mt.handles[f1].close()

    def test_missing_file_raises(self, tmp_path):
        missing = tmp_path / "does-not-exist.log"

        with pytest.raises(FileNotFoundError):
            MultiTail(filenames=[str(missing)])


class TestLongestStem:
    """Tests for MultiTail.longest_stem."""

    def test_single_file(self, tmp_path):
        f1 = make_file(tmp_path, "app.log")

        mt = MultiTail(filenames=[str(f1)])

        assert mt.longest_stem() == len("app")
        mt.handles[Path(f1)].close()

    def test_returns_longest_among_several(self, tmp_path):
        short = make_file(tmp_path, "a.log")
        longer = make_file(tmp_path, "database.log")

        mt = MultiTail(filenames=[str(short), str(longer)])

        assert mt.longest_stem() == len("database")
        for handle in mt.handles.values():
            handle.close()

    def test_stem_excludes_extension(self, tmp_path):
        f1 = make_file(tmp_path, "service.log")

        mt = MultiTail(filenames=[str(f1)])

        # "service" has 7 chars; the ".log" suffix is not counted.
        assert mt.longest_stem() == 7
        mt.handles[Path(f1)].close()


class TestFormatLine:
    """Tests for MultiTail.format_line."""

    def test_prefixes_line_with_stem(self, tmp_path):
        f1 = make_file(tmp_path, "web.log")

        mt = MultiTail(filenames=[str(f1)])
        result = mt.format_line(Path(f1), "hello\n")

        assert result == "web | hello\n"
        mt.handles[Path(f1)].close()

    def test_left_justifies_stem_to_longest(self, tmp_path):
        short = make_file(tmp_path, "a.log")
        longer = make_file(tmp_path, "database.log")

        mt = MultiTail(filenames=[str(short), str(longer)])
        result = mt.format_line(Path(short), "msg\n")

        # "a" padded to width of "database" (8 chars).
        assert result == "a        | msg\n"
        for handle in mt.handles.values():
            handle.close()

    def test_separator_is_pipe_with_spaces(self, tmp_path):
        f1 = make_file(tmp_path, "x.log")

        mt = MultiTail(filenames=[str(f1)])
        result = mt.format_line(Path(f1), "content")

        assert " | " in result
        mt.handles[Path(f1)].close()


class TestPeek:
    """Tests for the MultiTail._peek static method."""

    def test_returns_next_line_when_available(self, tmp_path):
        path = make_file(tmp_path, "a.log", "first\nsecond\n")

        with path.open() as handle:
            line = MultiTail._peek(handle)

        assert line == "first\n"

    def test_returns_none_at_eof(self, tmp_path):
        path = make_file(tmp_path, "a.log", "only\n")

        with path.open() as handle:
            handle.read()  # consume everything
            line = MultiTail._peek(handle)

        assert line is None

    def test_position_unchanged_when_no_new_line(self, tmp_path):
        """On EOF the read position is restored so later appends are seen."""
        path = make_file(tmp_path, "a.log", "data\n")

        with path.open() as handle:
            handle.read()
            before = handle.tell()
            MultiTail._peek(handle)
            after = handle.tell()

        assert before == after

    def test_advances_position_when_line_returned(self, tmp_path):
        path = make_file(tmp_path, "a.log", "first\nsecond\n")

        with path.open() as handle:
            MultiTail._peek(handle)
            assert handle.tell() == len("first\n")


class TestInitialTail:
    """Tests for MultiTail.initial_tail."""

    def test_yields_all_lines_when_below_catch_up(self, tmp_path):
        f1 = make_file(tmp_path, "a.log", "l1\nl2\nl3\n")

        mt = MultiTail(filenames=[str(f1)], catch_up=20)
        lines = list(mt.initial_tail())

        assert lines == ["a | l1\n", "a | l2\n", "a | l3\n"]
        mt.handles[Path(f1)].close()

    def test_yields_only_last_catch_up_lines(self, tmp_path):
        content = "".join(f"line{i}\n" for i in range(10))
        f1 = make_file(tmp_path, "a.log", content)

        mt = MultiTail(filenames=[str(f1)], catch_up=3)
        lines = list(mt.initial_tail())

        assert lines == ["a | line7\n", "a | line8\n", "a | line9\n"]
        mt.handles[Path(f1)].close()

    def test_yields_nothing_for_empty_file(self, tmp_path):
        f1 = make_file(tmp_path, "a.log", "")

        mt = MultiTail(filenames=[str(f1)], catch_up=5)
        lines = list(mt.initial_tail())

        assert lines == []
        mt.handles[Path(f1)].close()

    def test_combines_lines_from_multiple_files(self, tmp_path):
        f1 = make_file(tmp_path, "a.log", "a1\n")
        f2 = make_file(tmp_path, "bb.log", "b1\n")

        mt = MultiTail(filenames=[str(f1), str(f2)], catch_up=5)
        lines = list(mt.initial_tail())

        # Both stems padded to width of the longest stem ("bb" -> 2).
        assert lines == ["a  | a1\n", "bb | b1\n"]
        for handle in mt.handles.values():
            handle.close()

    def test_catch_up_zero_yields_nothing(self, tmp_path):
        f1 = make_file(tmp_path, "a.log", "l1\nl2\n")

        mt = MultiTail(filenames=[str(f1)], catch_up=0)
        lines = list(mt.initial_tail())

        assert lines == []
        mt.handles[Path(f1)].close()


class TestCheckLogRotation:
    """Tests for MultiTail._check_log_rotation."""

    def test_reopens_handle_when_inode_changes(self, tmp_path):
        f1 = make_file(tmp_path, "a.log", "old\n")

        mt = MultiTail(filenames=[str(f1)])
        path = Path(f1)
        original_handle = mt.handles[path]
        original_inode = mt.inodes[path]

        # Simulate rotation: replace the file with a new one (new inode).
        path.unlink()
        path.write_text("new\n")

        mt._check_log_rotation()

        assert mt.inodes[path] != original_inode
        assert mt.inodes[path] == path.stat().st_ino
        assert mt.handles[path] is not original_handle

        original_handle.close()
        mt.handles[path].close()

    def test_keeps_handle_when_inode_unchanged(self, tmp_path):
        f1 = make_file(tmp_path, "a.log", "x\n")

        mt = MultiTail(filenames=[str(f1)])
        path = Path(f1)
        original_handle = mt.handles[path]

        # Append without changing the inode.
        with path.open("a") as fh:
            fh.write("more\n")

        mt._check_log_rotation()

        assert mt.handles[path] is original_handle
        original_handle.close()

    def test_removes_path_when_file_disappears(self, tmp_path):
        f1 = make_file(tmp_path, "a.log", "x\n")
        f2 = make_file(tmp_path, "b.log", "y\n")

        mt = MultiTail(filenames=[str(f1), str(f2)])
        path1 = Path(f1)
        handle1 = mt.handles[path1]

        path1.unlink()

        mt._check_log_rotation()

        assert path1 not in mt.paths
        assert Path(f2) in mt.paths
        handle1.close()
        mt.handles[Path(f2)].close()


class TestTail:
    """Tests for MultiTail.tail (delegation to initial_tail then follow)."""

    def test_tail_starts_with_initial_lines(self, tmp_path):
        """tail() first yields the catch-up lines from initial_tail()."""
        content = "".join(f"line{i}\n" for i in range(5))
        f1 = make_file(tmp_path, "a.log", content)

        mt = MultiTail(filenames=[str(f1)], catch_up=2)
        gen = mt.tail()

        # The two initial lines come before follow() loops forever, so we only
        # pull those and then stop iterating.
        first = next(gen)
        second = next(gen)

        assert first == "a | line3\n"
        assert second == "a | line4\n"

        gen.close()  # ty: ignore[unresolved-attribute]  # tail() yields a generator
        mt.handles[Path(f1)].close()
