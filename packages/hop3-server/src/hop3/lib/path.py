# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import TYPE_CHECKING

__all__ = [
    "REJECTED_SUFFIX",
    "is_confined_to",
    "is_under",
    "prepend_to_path",
    "restore_on_failure",
]

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path


REJECTED_SUFFIX = ".rejected"


@contextmanager
def restore_on_failure(path: Path) -> Generator[None, None, None]:
    """Undo writes to ``path`` if the block raises, keeping the rejected copy.

    A candidate config has to be on disk while it is judged: `nginx -t` reads
    the whole tree, not a file handed to it. So a rejected one must not be
    left there — every later validation reads the same directory, and one
    app's bad vhost would fail every other app's deploy and every certificate
    renewal, naming none of them.

    On failure the candidate moves to ``<name>.rejected`` (outside the
    ``*.conf`` include glob, so the proxy never reads it) and the previous
    content comes back, which is also what the running proxy still has
    loaded. A later success clears the leftover.
    """
    rejected = path.with_name(path.name + REJECTED_SUFFIX)
    previous = path.read_bytes() if path.exists() else None
    try:
        yield
    except BaseException:
        if path.exists():
            path.replace(rejected)
        if previous is not None:
            path.write_bytes(previous)
        raise
    else:
        rejected.unlink(missing_ok=True)


def is_under(path: Path | str, root: Path | str) -> bool:
    """True if ``path`` is ``root`` or below it (both already normalised)."""
    p, r = str(path), str(root)
    return p == r or p.startswith(r + os.sep)


def is_confined_to(path: Path | str, root: Path | str) -> bool:
    """
    True if ``path`` resolves inside ``root``, symlinks included.

    Both sides are ``realpath``-ed before comparison. A lexical check
    (``normpath`` + ``startswith``) is **not** sufficient for a security
    boundary: an in-tree symlink such as ``src/data -> /etc`` is lexically
    inside the tree while actually pointing out of it, so the caller would go
    on to read, seed or delete through it.
    """
    return is_under(os.path.realpath(path), os.path.realpath(root))


def prepend_to_path(directories: list[Path | str], path: str = "") -> str:
    """
    Prepend directories to the PATH environment variable.

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
