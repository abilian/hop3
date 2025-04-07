# Copyright (c) 2023-2025, Abilian SAS

# TODO: duplicate code...

from __future__ import annotations

import os
from shutil import copy as cp

__all__ = ["cp", "shell"]


def shell(cmd):
    # TODO: better use subprocess
    print(cmd)
    status = os.system(cmd)
    if status != 0:
        msg = f"Command failed: {cmd!r}"
        raise RuntimeError(msg)
