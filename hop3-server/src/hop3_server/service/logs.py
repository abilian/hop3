# Copyright (c) 2023-2024, Abilian SAS
from __future__ import annotations

import time
from collections import deque
from collections.abc import Iterator
from pathlib import Path


def multi_tail(filenames, catch_up=20) -> Iterator:
    """Tails multiple log files."""

    # Seek helper
    def peek(handle):
        where = handle.tell()
        line = handle.readline()
        if not line:
            handle.seek(where)
            return None
        return line

    inodes = {}
    files = {}
    prefixes = {}

    # Set up current state for each log file
    for filename in filenames:
        path = Path(filename)
        prefixes[filename] = path.stem
        inodes[filename] = path.stat().st_ino
        files[filename] = path.open()
        files[filename].seek(0, 2)

    longest = max(map(len, prefixes.values()))

    # Grab a little history (if any)
    for filename in filenames:
        filepath = Path(filename)
        for line in deque(filepath.open(errors="ignore"), catch_up):
            yield f"{prefixes[filename].ljust(longest)} | {line}"

    while True:
        updated = False
        # Check for updates on every file
        for filename in filenames:
            line = peek(files[filename])
            if line:
                updated = True
                yield f"{prefixes[filename].ljust(longest)} | {line}"

        if not updated:
            time.sleep(1)
            # Check if logs rotated
            for filename in filenames:
                filepath = Path(filename)
                if filepath.exists():
                    if filepath.stat().st_ino != inodes[filename]:
                        files[filename] = filepath.open()
                        inodes[filename] = filepath.stat().st_ino
                else:
                    filenames.remove(filename)
