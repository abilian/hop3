# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from typing_extensions import Self


__all__ = ["UwsgiSettings"]


@dataclass(frozen=True)
class UwsgiSettings:
    values: list[tuple[str, str]] = field(default_factory=list)

    def add(self, key, value) -> None:
        """Add a key-value pair to the collection.

        Input:
        - key: The key associated with the value to be added.
        - value: The value to be added; it will be converted to a string before storage.
        """
        self.values.append((key, str(value)))

    def append(self, item) -> None:
        """Append an item to the collection by adding its elements.

        Input:
        - item: A tuple or list where the first element is the key and the second element is the value to be added.
        """
        self.add(item[0], item[1])

    def extend(self, items) -> None:
        """Append multiple items to the end of the list.

        Input:
        - items: An iterable containing elements to be added to the list.
        """
        for item in items:
            self.append(item)

    def __iadd__(self, items) -> Self:
        """In-place addition operator (+=) for the object.

        This is syntactic sugar for the 'extend' method.

        Input:
        - items: An iterable containing elements to be added to the current object.
        """
        self.extend(items)
        return self

    def write(self, path: Path) -> None:
        """Write the configuration values to a specified file path.

        Input:
        - path (Path): The file path where the configuration should be written.
        """
        with path.open("w") as h:
            h.write("[uwsgi]\n")
            for k, v in sorted(self.values):
                h.write(f"{k:s} = {v}\n")
