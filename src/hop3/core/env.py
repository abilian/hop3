from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Env(Mapping[str, Any]):
    data: dict[str, Any]

    def __setitem__(self, key: str, value: Any):
        self.data[key] = value

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def __delitem__(self, key: str):
        del self.data[key]

    def __contains__(self, item):
        return item in self.data

    def __len__(self):
        return len(self.data)

    def __iter__(self):
        return iter(self.data)

    def keys(self):
        return self.data.keys()

    def values(self):
        return self.data.values()

    def items(self):
        return self.data.items()

    def copy(self):
        return Env(self.data.copy())

    def update(self, other: Mapping[str, Any]):
        self.data.update(other)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def get_int(self, key: str, default: int = 0) -> int:
        value = self.get(key, default)
        match value:
            case int():
                return value
            case _:
                return int(value)

    def get_bool(self, key: str, default: bool = False) -> bool:
        value = self.get(key, default)
        match value:
            case bool():
                return value
            case str():
                return value.lower() in ["1", "on", "true", "enabled", "yes", "y"]
            case _:
                return bool(value)
