# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations


def setattr_frozen(self, key, value) -> None:
    if getattr(self, "__frozen__", False):
        raise AttributeError("Cannot set attribute on frozen instance")
    object.__setattr__(self, key, value)


def freeze(obj) -> None:
    cls = obj.__class__
    if cls.__setattr__ is not setattr_frozen:
        cls.__setattr__ = setattr_frozen
    object.__setattr__(obj, "__frozen__", True)
