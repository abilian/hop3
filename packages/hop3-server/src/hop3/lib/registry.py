# Copyright (c) 2024-2025, Abilian SAS
from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from attr import field, frozen

if TYPE_CHECKING:
    from collections.abc import ItemsView, Iterator

__all__ = ["lookup", "register", "registry"]

T = TypeVar("T")


@frozen
class Metadata:
    name: str = ""
    module: str = ""
    tag: str = ""
    extras: dict[str, Any] = field(factory=dict)


@frozen
class Registry:
    registered: dict[Any, Metadata] = field(factory=dict)

    def register(
        self,
        obj: T,
        name: str = "",
        module: str = "",
        tag: str = "",
        extras: dict | None = None,
    ) -> T:
        # obj is a class or function (register is used as a decorator); both
        # carry __name__/__module__, but the generic T can't prove it statically.
        if not name:
            name = getattr(obj, "__name__", "")
        if not module:
            module = getattr(obj, "__module__", "")
        if extras is None:
            extras = {}

        metadata = Metadata(name=name, module=module, tag=tag, extras=extras)
        self.registered[obj] = metadata
        return obj

    def lookup(self, key: object = "", tag: str = "") -> list:
        """
        Look up registered objects by name (str) or by class (type).

        ``key`` is typed ``object`` so the guard below stays live: lookups are
        also made with names coming from RPC payloads and CLI arguments.
        """
        # An if/elif ladder, not a match: `case type()` loses the class type.
        if key == "":
            objs = list(self.registered.items())
        elif isinstance(key, str):
            objs = self._lookup_by_name(key)
        elif isinstance(key, type):
            objs = self._lookup_by_type(key)
        else:
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

    def __iter__(self) -> Iterator[object]:
        return iter(self.registered)

    def items(self) -> ItemsView[Any, Metadata]:
        return self.registered.items()

    def __contains__(self, obj: object) -> bool:
        return obj in self.registered

    def get_metadata(self, obj: object) -> Metadata:
        return self.registered[obj]

    def clear(self) -> None:
        self.registered.clear()


registry = Registry()
register = registry.register
lookup = registry.lookup
