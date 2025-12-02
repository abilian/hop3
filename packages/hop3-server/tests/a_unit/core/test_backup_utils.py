# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-present Abilian SAS <contact@abilian.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for backup utility functions."""

from __future__ import annotations

import pytest

from hop3.core.backup import format_size


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
