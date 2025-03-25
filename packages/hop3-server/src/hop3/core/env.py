# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import field
from pathlib import Path
from typing import Any

from hop3.lib.freeze import freeze
from hop3.lib.settings import parse_settings


class Env(Mapping[str, str]):
    """Provides a dictionary-like environment variable handler with additional
    utility methods.

    This allows for storing, retrieving, and managing environment
    variables with support for additional operations like type
    conversion and file-based parsing.
    """

    _data: dict[str, str] = field(default_factory=dict)

    def __init__(self, data: Mapping[str, Any] | None = None) -> None:
        self._data = {}
        if data is None:
            data = {}

        for k, v in data.items():
            self._data[k] = str(v)

        freeze(self)

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = str(value)

    def __getitem__(self, key: str) -> str:
        return self._data[key]

    def __delitem__(self, key: str) -> None:
        del self._data[key]

    def __contains__(self, item) -> bool:
        return item in self._data

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self) -> Iterator:
        return iter(self._data)

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()

    def copy(self) -> Env:
        return Env(self._data.copy())

    def update(self, other: Mapping[str, Any]) -> None:
        for k, v in other.items():
            self._data[k] = str(v)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    #
    # Additional API
    #
    def get_int(self, key: str, default: int = 0) -> int:
        value = self.get(key, default)
        match value:
            case int():
                return value
            case _:
                return int(value)

    def get_bool(self, key: str, *, default: bool = False) -> bool:
        value = self.get(key, default)
        match value:
            case bool():
                return value
            case str():
                return value.lower() in {"1", "on", "true", "enabled", "yes", "y"}
            case _:
                return bool(value)

    def get_path(self, key: str, default: str | Path = "") -> Path:
        value = self.get(key, default)
        match value:
            case str():
                return Path(value)
            case Path():
                return value
            case _:
                # XXX: keep? Or raise an error?
                return Path(str(value))

    def parse_settings(self, env_file: Path) -> None:
        if env_file.exists():
            self.update(parse_settings(env_file))
