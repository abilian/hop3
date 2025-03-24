# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# Copy/pasted from contextlib.py in Python 3.11
from __future__ import annotations

import os
from contextlib import AbstractContextManager
from pathlib import Path


class chdir(AbstractContextManager):  # noqa: N801
    """Non thread-safe context manager to change the current working directory.

    This context manager is used to temporarily change the current working
    directory to a specified path and then revert back to the original
    directory upon exiting the context.

    Input:
    - path (Path | str): The target directory path to change the current
      working directory to. It can be a Path object or a string representing
      the path.

    The class does not explicitly return any values but ensures that the
    working directory is reverted back to its original state upon exiting
    the context.

    Raises:
    - OSError: If changing the directory fails either while entering or
      exiting the context.
    - IndexError: If there is an attempt to pop from an empty list when
      reverting the directory.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = path
        self._old_cwd: list[Path] = []

    def __enter__(self) -> None:
        try:
            # Save the current working directory to revert back later
            self._old_cwd.append(Path().absolute())
        except OSError as e:
            # Handle any OS-related errors gracefully
            print(f"Ignoring error in chdir() enter:\n{e}")
        # Change to the new directory
        os.chdir(self.path)

    def __exit__(self, *_excinfo) -> None:
        try:
            # Revert back to the original directory
            os.chdir(self._old_cwd.pop())
        except (OSError, IndexError) as e:
            # Handle errors during the directory change or list pop operation
            print(f"Ignoring error in chdir() exit:\n{e}")
