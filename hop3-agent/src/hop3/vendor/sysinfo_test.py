# Copyright (c) 2023-2024, Abilian SAS

from hop3.vendor.sysinfo import SysInfo


def test_sysinfo():
    sys_info = SysInfo()
    assert sys_info.platform_name() in {"Linux", "Darwin"}
