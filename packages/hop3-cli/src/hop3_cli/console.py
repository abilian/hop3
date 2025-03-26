from __future__ import annotations

import sys


def err(*args):
    """Print to stderr."""
    # TODO: rename as this is misleading.
    print(*args, file=sys.stderr)


def dim(text: str) -> str:
    return "\x1b[0;37m" + text + "\x1b[0m"
