# Copyright (c) 2023-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Defense-in-depth tests for App.app_path.

Wave-1 security audit: even if RPC-boundary validation is bypassed,
``app_path`` must refuse to resolve paths that escape ``APP_ROOT``.
"""

from __future__ import annotations

import pytest

from hop3.orm import App


@pytest.mark.parametrize(
    "bad_name",
    [
        "..",
        "../etc",
        "../../etc/passwd",
        "/absolute/path",
        "rel/with/slash",
        "rel\\with\\backslash",
        ".hidden",
        "",
    ],
)
def test_app_path_rejects_traversal(bad_name: str) -> None:
    app = App(name=bad_name)
    with pytest.raises(ValueError, match="Unsafe app name"):
        _ = app.app_path


def test_app_path_accepts_well_formed_name() -> None:
    app = App(name="myapp")
    # Should return a Path under APP_ROOT without raising.
    path = app.app_path
    assert path.name == "myapp"
