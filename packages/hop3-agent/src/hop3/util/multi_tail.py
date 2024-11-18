# Copyright (c) 2024, Abilian SAS
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
        self._open_files()

    def _open_files(self):
        for filename in self.filenames:
            path = Path(filename)
            self.paths.append(path)
            self.inodes[path] = path.stat().st_ino
            self.handles[path] = path.open()
            self.handles[path].seek(0, 2)

    def tail(self) -> Iterator:
        yield from self.initial_tail()
        yield from self.follow()

    def initial_tail(self) -> Iterator:
        for path in self.paths:
            for line in deque(path.open(errors="ignore"), self.catch_up):
                yield self.format_line(path, line)

    def follow(self) -> Iterator:
        while True:
            for path in self.paths:
                line = self._peek(self.handles[path])
                if line:
                    yield self.format_line(path, line)

            time.sleep(1)
            self._check_log_rotation()

    def longest_stem(self) -> int:
        return max(len(path.stem) for path in self.paths)

    def format_line(self, path: Path, line: str) -> str:
        return f"{path.stem.ljust(self.longest_stem())} | {line}"

    def _peek(self, handle):
        where = handle.tell()
        line = handle.readline()
        if not line:
            handle.seek(where)
            return None
        return line

    def _check_log_rotation(self):
        for path in self.paths:
            if path.exists():
                if path.stat().st_ino != self.inodes[path]:
                    self.handles[path] = path.open()
                    self.inodes[path] = path.stat().st_ino
            else:
                self.paths.remove(path)
