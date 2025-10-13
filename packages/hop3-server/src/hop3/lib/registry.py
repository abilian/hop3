# Copyright (c) 2024-2025, Abilian SAS
from __future__ import annotations

from typing import Any

from attr import field, frozen

__all__ = ["lookup", "register", "registry"]


@frozen
class Metadata:
    name: str = ""
    module: str = ""
    tag: str = ""
    extras: dict[str, Any] = field(factory=dict)


@frozen
class Registry:
    registered: dict[Any, Metadata] = field(factory=dict)

    def register(self, obj, name="", module="", tag="", extras=None):
        if not name:
            name = obj.__name__
        if not module:
            module = obj.__module__
        if extras is None:
            extras = {}

        metadata = Metadata(name=name, module=module, tag=tag, extras=extras)
        self.registered[obj] = metadata
        return obj

    def lookup(self, key: str | type = "", tag: str = "") -> list:
        match key:
            case "":
                objs = list(self.registered.items())
            case str():
                objs = self._lookup_by_name(key)
            case type():
                objs = self._lookup_by_type(key)
            case _:
                msg = f"Invalid key type: {type(key)}"
                raise TypeError(msg)

        if tag:
            return [obj for obj, metadata in objs if tag == metadata.tag]
        return [obj for obj, _metadata in objs]

    def _lookup_by_name(self, name: str) -> list[tuple[Any, Metadata]]:
        result = []
        for obj, metadata in self.registered.items():
            if metadata.name == name:
                result.append((obj, metadata))
        return result

    def _lookup_by_type(self, cls: type) -> list[tuple[Any, Metadata]]:
        result: list[tuple[Any, Metadata]] = []
        for obj, metadata in self.registered.items():
            if isinstance(obj, type):
                if issubclass(obj, cls):
                    result.append((obj, metadata))
            elif isinstance(obj, cls):
                result.append((obj, metadata))

        return result

    def __iter__(self):
        return iter(self.registered)

    def items(self):
        return self.registered.items()

    def __contains__(self, obj):
        return obj in self.registered

    def get_metadata(self, obj: Any) -> Metadata:
        return self.registered[obj]

    def clear(self):
        self.registered.clear()


registry = Registry()
register = registry.register
lookup = registry.lookup
