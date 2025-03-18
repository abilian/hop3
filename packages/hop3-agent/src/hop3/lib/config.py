# Copyright (c) 2024-2025, Abilian SAS
"""
Copy/pasted from Starlette, with some changes.
"""

from __future__ import annotations

import os
import typing


class Undefined:
    pass


class EnvironError(Exception):
    pass


class Environ(typing.MutableMapping[str, str]):
    def __init__(self, environ: typing.MutableMapping[str, str] = os.environ):
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

    def __iter__(self) -> typing.Iterator[str]:
        return iter(self._environ)

    def __len__(self) -> int:
        return len(self._environ)


environ = Environ()

T = typing.TypeVar("T")


class Config:
    def __init__(
        self,
        environ: typing.Mapping[str, str] = environ,
        env_prefix: str = "",
    ) -> None:
        self.environ = environ
        self.env_prefix = env_prefix
        self.file_values: dict[str, str] = {}

    @typing.overload
    def __call__(self, key: str, *, default: None) -> str | None: ...

    @typing.overload
    def __call__(self, key: str, cast: type[T], default: T = ...) -> T: ...

    @typing.overload
    def __call__(self, key: str, cast: type[str] = ..., default: str = ...) -> str: ...

    @typing.overload
    def __call__(
        self,
        key: str,
        cast: typing.Callable[[typing.Any], T] = ...,
        default: typing.Any = ...,
    ) -> T: ...

    @typing.overload
    def __call__(
        self, key: str, cast: type[str] = ..., default: T = ...
    ) -> T | str: ...

    def __call__(
        self,
        key: str,
        cast: typing.Callable[[typing.Any], typing.Any] | None = None,
        default: typing.Any = Undefined,
    ) -> typing.Any:
        return self.get(key, cast, default)

    def get(
        self,
        key: str,
        cast: typing.Callable[[typing.Any], typing.Any] | None = None,
        default: typing.Any = Undefined,
    ) -> typing.Any:
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

    def _perform_cast(
        self,
        key: str,
        value: typing.Any,
        cast: typing.Callable[[typing.Any], typing.Any] | None = None,
    ) -> typing.Any:
        if cast is None or value is None:
            return value
        elif cast is bool and isinstance(value, str):
            mapping = {"true": True, "1": True, "false": False, "0": False}
            value = value.lower()
            if value not in mapping:
                msg = f"Config '{key}' has value '{value}'. Not a valid bool."
                raise ValueError(msg)
            return mapping[value]
        try:
            return cast(value)
        except (TypeError, ValueError):
            msg = f"Config '{key}' has value '{value}'. Not a valid {cast.__name__}."
            raise ValueError(msg)
