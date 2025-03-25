# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
# SPDX-License-Identifier: MIT

from __future__ import annotations

from hop3.main import main


def test_cli() -> None:
    try:
        main(["help"])
    except SystemExit as e:
        assert e.code == 0  # noqa: PT017
