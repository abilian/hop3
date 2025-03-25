# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

# ruff: noqa: PLC2801


def setattr_frozen(self, key, value) -> None:
    """Set an attribute on an instance, raising an error if the instance is
    frozen.

    Input:
    - key: The name of the attribute to set.
    - value: The value to set for the attribute.
    """
    if getattr(self, "__frozen__", False):  # Check if the instance is frozen
        msg = "Cannot set attribute on frozen instance"
        raise AttributeError(msg)
    object.__setattr__(self, key, value)


def freeze(obj) -> None:
    """Freezes an object to prevent further modifications by overriding its
    __setattr__ method.

    Input:
    - obj: The object to be frozen. It should be an instance of a class, not a basic data type.

    This modifies the class of the given object to override the __setattr__ method with a custom
    method, preventing any attribute changes. It also sets an internal "__frozen__" attribute to True to
    indicate the object's frozen state.
    """
    cls = obj.__class__
    if cls.__setattr__ is not setattr_frozen:
        # Only override __setattr__ if it hasn't been done already
        cls.__setattr__ = setattr_frozen
    # Set an internal flag to indicate the object is frozen
    object.__setattr__(obj, "__frozen__", True)
