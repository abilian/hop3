# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-present Abilian SAS <contact@abilian.com>
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for backup utility functions."""

from __future__ import annotations

import pytest

from hop3.core.backup import _matches_exclude, _strip_arc_root, format_size


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        (500, "500.0 B"),
        (1024, "1.0 KB"),
        (1536, "1.5 KB"),
        (1024 * 1024, "1.0 MB"),
        (1024 * 1024 * 1024, "1.0 GB"),
    ],
)
def test_format_size(size: int, expected: str):
    """Test format_size utility with various byte values."""
    assert format_size(size) == expected


@pytest.mark.parametrize(
    ("arcname", "root", "expected"),
    [
        ("src", "src", ""),
        ("src/app.py", "src", "app.py"),
        ("src/cache/x", "src", "cache/x"),
        ("data/db.sqlite", "data", "db.sqlite"),
        ("other/x", "src", "other/x"),  # not under root → unchanged
    ],
)
def test_strip_arc_root(arcname: str, root: str, expected: str):
    assert _strip_arc_root(arcname, root) == expected


@pytest.mark.parametrize(
    ("rel", "patterns", "expected"),
    [
        ("app.tmp", ["*.tmp"], True),  # basename glob
        ("sub/app.tmp", ["*.tmp"], True),  # basename glob, nested
        ("cache/big.bin", ["cache/*"], True),  # full-path glob
        ("a/node_modules/x", ["node_modules"], True),  # path segment
        ("keep.py", ["*.tmp", "cache/*"], False),  # no match
        ("", ["*"], False),  # empty rel (the root itself) never excluded
        ("logs/x", ["logs/"], True),  # trailing slash tolerated
    ],
)
def test_matches_exclude(rel: str, patterns: list[str], expected: bool):
    assert _matches_exclude(rel, patterns) is expected
