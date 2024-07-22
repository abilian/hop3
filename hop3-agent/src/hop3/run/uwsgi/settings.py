# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from typing_extensions import Self

__all__ = ["UwsgiSettings"]


@dataclass(frozen=True)
class UwsgiSettings:
    values: list[tuple[str, str]] = field(default_factory=list)

    def add(self, key, value) -> None:
        self.values.append((key, str(value)))

    def append(self, item) -> None:
        self.add(item[0], item[1])

    def extend(self, items) -> None:
        for item in items:
            self.append(item)

    def __iadd__(self, items) -> Self:
        self.extend(items)
        return self

    def write(self, path: Path):
        with path.open("w") as h:
            h.write("[uwsgi]\n")
            for k, v in sorted(self.values):
                h.write(f"{k:s} = {v}\n")
        return path
