# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest

from hop3.util.freeze import freeze


class A:
    def __init__(self, x) -> None:
        self.x = x
        freeze(self)


def test_frozen() -> None:
    a = A(1)
    with pytest.raises(AttributeError):
        a.x = 2
