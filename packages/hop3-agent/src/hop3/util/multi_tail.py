# Copyright (c) 2024-2025, Abilian SAS
# Cf. https://stackoverflow.com/questions/5725051/tail-multiple-logfiles-in-python
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass(frozen=True)
class MultiTail:
    # List of filenames or paths to tail
    filenames: list[str | Path]

    # Number of lines to read from the beginning of the file
    catch_up: int = 20

    # Paths to files
    paths: list[Path] = field(default_factory=list)

    # Inodes to detect log rotation
    inodes: dict[Path, int] = field(default_factory=dict)

    # Open file handles
    handles: dict[Path, TextIO] = field(default_factory=dict)

    def __post_init__(self):
        for filename in self.filenames:
            path = Path(filename)
            self.paths.append(path)
            self.inodes[path] = path.stat().st_ino
            self.handles[path] = path.open()
            self.handles[path].seek(0, 2)

    def tail(self) -> Iterator:
        """Continuously yields lines from the end of a file or a data stream.

        This mimics the behavior of the Unix 'tail -f'
        command by continuously providing new lines as they are appended to the
        file or data stream.

        Returns:
        - An iterator that yields lines from the end of a file or data stream.
        """
        yield from self.initial_tail()  # Yield lines present initially in the data source
        yield from self.follow()  # Continuously yield new lines appended to the data source

    def initial_tail(self) -> Iterator:
        """Generate an iterator of formatted lines from multiple file paths.

        Iterates over each file path specified in the self.paths attribute,
        reads lines using a deque to handle a fixed number of recent lines (specified by self.catch_up),
        and yields formatted lines using the self.format_line() method.

        Returns:
        - An iterator that yields formatted lines from the files.
        """
        for path in self.paths:
            # Open the file, ignoring errors, and use a deque to process the last 'catch_up' lines
            for line in deque(path.open(errors="ignore"), self.catch_up):
                yield self.format_line(path, line)

    def follow(self) -> Iterator:
        """Continuously monitor log files for new entries and yields formatted
        lines.

        Returns:
        - An iterator that yields formatted lines from updated log files.
        """
        while True:
            for path in self.paths:
                line = self._peek(self.handles[path])
                if line:
                    yield self.format_line(path, line)

            # Pause iteration to avoid busy-waiting
            time.sleep(1)
            # Check and handle log file rotation
            self._check_log_rotation()

    def longest_stem(self) -> int:
        """Calculate the length of the longest stem in a list of paths.

        Returns:
            int: The length of the longest stem found in the paths.
        """
        return max(len(path.stem) for path in self.paths)

    def format_line(self, path: Path, line: str) -> str:
        """Format a line by prefixing it with the stem of a given file path.

        Input:
        - path: A Path object representing the file path whose stem is to be used.
        - line: A string that represents the line to be formatted.

        Returns:
        - A string that combines the left-justified stem of the file path and the line, separated by ' | '.
        """
        # Constructs the formatted output by left-justifying the file path stem
        # and appending the line with a separator.
        return f"{path.stem.ljust(self.longest_stem())} | {line}"

    @staticmethod
    def _peek(handle):
        where = handle.tell()
        line = handle.readline()
        if not line:
            handle.seek(where)
            return None
        return line

    def _check_log_rotation(self):
        """Checks and handles log file rotation by reopening files if their
        inode has changed.

        This iterates over the paths being monitored for log rotation.
        If a path exists and its inode number differs from the
        previously recorded value, it updates the file handle and inode.
        If the path no longer exists, it removes the path from the list
        of monitored paths.
        """
        for path in self.paths:
            if path.exists():
                # Check if the inode of the path has changed
                if path.stat().st_ino != self.inodes[path]:
                    # Reopen the file and update the inode information
                    self.handles[path] = path.open()
                    self.inodes[path] = path.stat().st_ino
            else:
                # Remove path from monitored list if it no longer exists
                self.paths.remove(path)
