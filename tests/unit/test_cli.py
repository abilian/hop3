# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-License-Identifier: MIT

from __future__ import annotations

from hop3.main import main


def test_cli():
    try:
        main(["help"])
    except SystemExit as e:
        assert e.code == 0
