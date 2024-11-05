# Copyright (c) 2024, Abilian SAS

# ruff: noqa: PLR2004
from __future__ import annotations

from hop3.util.delegate import delegate


@delegate("_n", int)
class NumberWrapper(int):
    """
    NumberWrapper
    """

    def __init__(self, n):
        self._n = n


def test_delegate():
    n = NumberWrapper(2)
    assert n + 1 == 3
    assert n * 3 == 6


def test_docstring():
    assert "NumberWrapper" in NumberWrapper.__doc__


@delegate("_contents", list)
@delegate("_number", int)
class NumberedBag:  # type: ignore
    def __init__(self, contents=None, number=1):
        self._contents = contents or []
        self._number = number

    def __delitem__(self, key):
        del self._contents[key]


def test_double_delegation():
    bag = NumberedBag(["a", "b", "c"], 12)
    assert len(bag) == 3
    assert bag / 2 == 6
    assert 2**bag == 4096
    assert bag[1] == "b"
    del bag[1]
    assert bag[1] == "c"
    bag[0] = "A"
    assert bag[0] == "A"
