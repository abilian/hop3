# Copyright (c) 2023-2024, Abilian SAS

from devtools import debug

from hop3.vendor.sysinfo import get_system_info


def test_sysinfo():
    d = get_system_info()
    debug(d)
    assert "Processor" in d
