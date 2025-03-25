# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def prepend_to_path(directories: list[Path | str], path: str = "") -> str:
    """Prepend directories to the PATH environment variable.

    Input:
    - directories: A list of directories (Path or str) to be added to the PATH.
    - path: An optional string representing the PATH to update. If not provided, defaults to the current PATH environment variable.

    Returns:
    - A string representing the updated PATH with the specified directories prepended.
    """
    if not path:
        # Use the current PATH environment variable if no path is provided
        path = os.environ["PATH"]

    current_path = path.split(":")
    new_path = []
    for directory in [str(d) for d in directories]:
        if directory in current_path:
            continue
        new_path.append(directory)
    new_path.extend(current_path)
    return ":".join(new_path)
