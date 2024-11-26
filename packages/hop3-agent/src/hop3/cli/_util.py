# Copyright (c) 2024, Abilian SAS
# Utils
from __future__ import annotations

import fcntl
import os


def make_nonblocking(fd) -> None:
    """Put the file descriptor *fd* into non-blocking mode if
    possible.
    """
    flags = fcntl.fcntl(fd, fcntl.F_GETFL, 0)
    if not bool(flags & os.O_NONBLOCK):
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
