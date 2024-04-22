# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import os
import typing

if typing.TYPE_CHECKING:  # pragma: no cover
    from pathlib import Path


def prepend_to_path(directories: list[Path | str], path: str = "") -> str:
    """Update the PATH environment variable."""
    if not path:
        path = os.environ["PATH"]

    current_path = path.split(":")
    new_path = []
    for directory in [str(d) for d in directories]:
        if directory in current_path:
            continue
        new_path.append(directory)
    new_path.extend(current_path)
    return ":".join(new_path)
