"""Easy delegation with composition

- https://github.com/hsharrison/smartcompose
- Licensed under terms of the MIT License (see LICENSE.txt)
- Copyright (c) 2014 Henry S. Harrison, henry.schafer.harrison@gmail.com
"""
from __future__ import annotations

from functools import partial, partialmethod


def _call_delegated_method(attribute_name, self, method_name, *args, **kwargs):
    return getattr(getattr(self, attribute_name), method_name)(*args, **kwargs)


def delegate(attribute_name, attribute_type):
    """
    Decorator factory to delegate methods to an attribute.

    Decorate a class to map every method in `method_names` to the attribute `attribute_name`.
    """
    call_attribute_method = partial(_call_delegated_method, attribute_name)

    def decorate(class_):
        for method_name in dir(attribute_type):
            if hasattr(class_, method_name):
                continue
            method = getattr(attribute_type, method_name)
            if callable(method):
                setattr(
                    class_,
                    method_name,
                    partialmethod(call_attribute_method, method_name),
                )

        return class_

    return decorate
