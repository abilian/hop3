# Copyright (c) 2023-2025, Abilian SAS

from __future__ import annotations

from hop3.vendor.sysinfo import SysInfo


def test_sysinfo() -> None:
    sys_info = SysInfo()
    # We only support Linux and macOS
    assert sys_info.platform_name() in {"Linux", "Darwin"}
