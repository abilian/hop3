# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
# SPDX-License-Identifier: MIT

from __future__ import annotations

from hop3.util import prepend_to_path


def test_path_no_change() -> None:
    path = "/usr/local/sbin:/usr/sbin:/sbin:/usr/local/bin:/usr/bin:/bin"
    result = prepend_to_path(["/usr/local/bin", "/usr/bin", "/bin"], path)
    assert result == path


def test_path_change() -> None:
    path = "/usr/local/bin:/usr/bin:/bin"
    result = prepend_to_path(["/usr/local/sbin", "/bin"], path)
    assert result == "/usr/local/sbin:/usr/local/bin:/usr/bin:/bin"
