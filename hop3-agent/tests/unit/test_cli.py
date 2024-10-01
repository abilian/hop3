# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
# SPDX-License-Identifier: MIT

from __future__ import annotations

from hop3.main import main


def test_cli():
    try:
        main(["help"])
    except SystemExit as e:
        assert e.code == 0
