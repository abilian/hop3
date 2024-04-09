import pytest

from hop3.util.freeze import freeze


class A:
    def __init__(self, x):
        self.x = x
        freeze(self)


def test_frozen():
    a = A(1)
    with pytest.raises(AttributeError):
        a.x = 2
