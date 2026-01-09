# Copyright (c) 2024-2025, Abilian SAS
"""
Copy/pasted from Starlette, with some changes.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator, Mapping, MutableMapping
from pathlib import Path
from typing import Any, TypeVar, overload

import toml


class Undefined:
    pass


_undefined = Undefined()


class EnvironError(Exception):
    pass


class Environ(MutableMapping[str, str]):
    """
    A wrapper around os.environ that prevents setting or deleting values that have already been read.
    """

    def __init__(self, environ: MutableMapping[str, str] = os.environ):
        self._environ = environ
        self._has_been_read: set[str] = set()

    def __getitem__(self, key: str) -> str:
        self._has_been_read.add(key)
        return self._environ.__getitem__(key)

    def __setitem__(self, key: str, value: str) -> None:
        if key in self._has_been_read:
            msg = f"Attempting to set environ['{key}'], but the value has already been read."
            raise EnvironError(msg)
        self._environ.__setitem__(key, value)

    def __delitem__(self, key: str) -> None:
        if key in self._has_been_read:
            msg = f"Attempting to delete environ['{key}'], but the value has already been read."
            raise EnvironError(msg)
        self._environ.__delitem__(key)

    def __iter__(self) -> Iterator[str]:
        return iter(self._environ)

    def __len__(self) -> int:
        return len(self._environ)


environ = Environ()

T = TypeVar("T")


class Config:
    def __init__(
        self,
        environ: Mapping[str, str] = environ,
        file: Path | None = None,
        env_prefix: str = "",
    ) -> None:
        self.environ = environ
        self.env_prefix = env_prefix
        self.file_values: dict[str, str] = {}
        if file is not None:
            self._parse_file(file)

    @overload
    def __call__(self, key: str, *, default: None) -> str | None: ...

    @overload
    def __call__(self, key: str, cast: type[T], default: T = ...) -> T: ...

    @overload
    def __call__(self, key: str, cast: type[str] = ..., default: str = ...) -> str: ...

    @overload
    def __call__(
        self,
        key: str,
        cast: Callable[[Any], T] = ...,
        default: Any = ...,
    ) -> T: ...

    @overload
    def __call__(
        self, key: str, cast: type[str] = ..., default: T = ...
    ) -> T | str: ...

    def __call__(
        self,
        key: str,
        cast: Callable[[Any], Any] | None = None,
        default: Any = Undefined,
    ) -> Any:
        return self.get(key, cast, default)

    def get(
        self,
        key: str,
        cast: Callable[[Any], Any] | None = None,
        default: Any = Undefined,
    ) -> Any:
        key = self.env_prefix + key
        if key in self.environ:
            value = self.environ[key]
            return self._perform_cast(key, value, cast)
        if key in self.file_values:
            value = self.file_values[key]
            return self._perform_cast(key, value, cast)
        if default is not Undefined:
            return self._perform_cast(key, default, cast)
        msg = f"Config '{key}' is missing, and has no default."
        raise KeyError(msg)

    def get_str(self, key: str, default: Any = Undefined) -> str:
        return self.get(key, str, default)

    def get_int(self, key: str, default: Any = Undefined) -> int:
        return self.get(key, int, default)

    def get_float(self, key: str, default: Any = Undefined) -> float:
        return self.get(key, float, default)

    def get_bool(self, key: str, default: Any = Undefined) -> bool:
        return self.get(key, bool, default)

    def get_path(self, key: str, default: Any = Undefined) -> Path:
        return self.get(key, Path, default)

    def _perform_cast(
        self,
        key: str,
        value: Any,
        cast: Callable[[Any], Any] | None = None,
    ) -> Any:
        if cast is None or value is None:
            return value
        if cast is bool and isinstance(value, str):
            mapping = {"true": True, "1": True, "false": False, "0": False}
            value = value.lower()
            if value not in mapping:
                msg = f"Config '{key}' has value '{value}'. Not a valid bool."
                raise ValueError(msg)
            return mapping[value]
        try:
            return cast(value)
        except (TypeError, ValueError):
            cast_name = getattr(cast, "__name__", repr(cast))
            msg = f"Config '{key}' has value '{value}'. Not a valid {cast_name}."
            raise ValueError(msg)

    def _parse_file(self, file: Path) -> None:
        assert file.suffix == ".toml"

        with file.open() as fd:
            content = toml.load(fd)

        for key, value in content.items():
            self.file_values[key.upper()] = value
