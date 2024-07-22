# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import stat
from pathlib import Path


def make_executable(file: Path | str) -> None:
    """Make file executable by the user."""
    path = Path(file)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
