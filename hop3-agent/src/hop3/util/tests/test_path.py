# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
# SPDX-License-Identifier: MIT

from __future__ import annotations

from hop3.util.path import prepend_to_path


def test_path_no_change():
    path = "/usr/local/sbin:/usr/sbin:/sbin:/usr/local/bin:/usr/bin:/bin"
    result = prepend_to_path(["/usr/local/bin", "/usr/bin", "/bin"], path)
    assert result == path


def test_path_change():
    path = "/usr/local/bin:/usr/bin:/bin"
    result = prepend_to_path(["/usr/local/sbin", "/bin"], path)
    assert result == "/usr/local/sbin:/usr/local/bin:/usr/bin:/bin"
