# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS

# Copy/pasted from contextlib.py in Python 3.11

from __future__ import annotations

import os
from contextlib import AbstractContextManager
from pathlib import Path


class chdir(AbstractContextManager):  # noqa: N801
    """Non thread-safe context manager to change the current working
    directory."""

    def __init__(self, path: Path | str) -> None:
        self.path = path
        self._old_cwd: list[str] = []

    def __enter__(self) -> None:
        try:
            self._old_cwd.append(os.getcwd())
        except OSError as e:
            print(f"Ignoring error in chdir() enter:\n{e}")
        os.chdir(self.path)

    def __exit__(self, *_excinfo) -> None:
        try:
            os.chdir(self._old_cwd.pop())
        except (OSError, IndexError) as e:
            print(f"Ignoring error in chdir() exit:\n{e}")
