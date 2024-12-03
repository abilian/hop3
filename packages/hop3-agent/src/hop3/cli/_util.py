# Copyright (c) 2024, Abilian SAS
# Utils
from __future__ import annotations

import fcntl
import os


def make_nonblocking(fd) -> None:
    """Put the file descriptor *fd* into non-blocking mode if possible.

    Input:
    - fd: A file descriptor for which the non-blocking mode is to be set.
    """
    # Retrieve the current file status flags for the file descriptor
    flags = fcntl.fcntl(fd, fcntl.F_GETFL, 0)

    # Check if the non-blocking flag is not already set
    if not bool(flags & os.O_NONBLOCK):
        # Set the non-blocking flag for the file descriptor
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
