# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The one subtree of an app that the web server reads off disk.

An app's source is extracted owner-only: `extract_archive_to_dir` masks every
member's mode with ``0o700``, so a file that was 0644 in the repository lands
0600 on the box. That is the right default — an app's code and its `.env` are
not public, and per-app UID separation (ADR 055) makes that matter more, not
less — but it is wrong for the files the web server is *supposed* to publish,
because nginx's workers run as `www-data` and get ``403 Forbidden`` on a 0600
file.

Two kinds of app are served off disk this way, and the second only became one
when php-fpm arrived:

- a **static** site, which nginx serves entirely;
- a **php-fpm** app, whose document root nginx serves for everything that is
  not a `.php` script — every stylesheet, script and image the app ships.

So the grant is scoped to the document root and no wider. Everything above it
keeps its 0600, which is the point: a Laravel app's `.env` sits one level up
from `public/`, and nginx's `root` is not the only thing that should be
stopping a request from reaching it.

A volume beneath the document root (WordPress's `wp-content/uploads`) is
served through its link, and ``chmod -R`` does not follow links, so its
storage is granted too. Only a link into the app's own volume storage: an app
can plant a link anywhere, and following it would publish whatever it names.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

from hop3.lib import Diagnosis, abort_with_diagnosis, log
from hop3.lib.path import is_confined_to

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

__all__ = ["grant_web_server_read"]

#: Read-only and world-readable: a tree served from here needs no grant, and
#: a chmod on it fails.
_NIX_STORE = Path("/nix/store")


def grant_web_server_read(served: Path, storage_roots: Iterable[Path] = ()) -> None:
    """
    Let the web server read the tree it is about to serve.

    ``chmod -R a+rX`` grants read to all, plus traverse on directories only,
    so a data file does not come out executable. A link beneath ``served`` that
    resolves under one of ``storage_roots`` (the app's volume storage) is
    granted as well.

    A tree in the Nix store is already world-readable and cannot be chmod'ed,
    so it is left alone. Any other failure stops the deploy: it was logged and
    the deploy carried on, to an app that deployed green and answered 403 on
    every asset. The store was the only reason the grant was best-effort.
    """
    if not served.exists() or served.resolve().is_relative_to(_NIX_STORE):
        return
    for tree in [served, *_linked_storage(served, list(storage_roots))]:
        try:
            subprocess.run(
                ["chmod", "-R", "a+rX", str(tree)],
                check=True,
                capture_output=True,
                text=True,
            )
            log(f"Granted web server read access to {tree}", level=3)
        except subprocess.CalledProcessError as e:
            _refuse_unreadable(tree, (e.stderr or "").strip() or str(e))
        except OSError as e:
            _refuse_unreadable(tree, str(e))


def _refuse_unreadable(tree: Path, reason: str) -> NoReturn:
    abort_with_diagnosis(
        Diagnosis(
            component="Web server",
            action=f"read {tree}",
            reason=f"`chmod -R a+rX {tree}` failed: {reason}",
            hint=(
                "fix the ownership of that tree (the deploy runs as the hop3 "
                "user), then deploy again"
            ),
        )
    )


def _linked_storage(served: Path, storage_roots: list[Path]) -> Iterator[Path]:
    """The storage behind each link in ``served`` that lands in a storage root."""
    for directory, dirs, files in os.walk(served):
        for name in [*dirs, *files]:
            path = Path(directory) / name
            if path.is_symlink() and path.is_dir():
                if any(is_confined_to(path, root) for root in storage_roots):
                    yield Path(os.path.realpath(path))
