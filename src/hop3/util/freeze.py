# Copyright (c) 2023-2024, Abilian SAS

from devtools import debug


def setattr_frozen(self, key, value):
    debug(self, key, value)
    if getattr(self, "__frozen__", False):
        raise AttributeError("Cannot set attribute on frozen instance")
    object.__setattr__(self, key, value)


def freeze(obj):
    cls = obj.__class__
    if cls.__setattr__ is not setattr_frozen:
        cls.__setattr__ = setattr_frozen
    object.__setattr__(obj, "__frozen__", True)
