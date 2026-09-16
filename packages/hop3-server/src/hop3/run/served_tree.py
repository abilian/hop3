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
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from hop3.lib import log

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["grant_web_server_read"]


def grant_web_server_read(served: Path) -> None:
    """
    Let the web server read the tree it is about to serve.

    ``chmod -R a+rX`` grants read to all, plus traverse on directories only,
    so a data file does not come out executable.

    Best-effort by design: a read-only artifact (a Nix store path, already
    world-readable) cannot be chmod'ed and does not need to be. A failure is
    logged rather than fatal — but it is logged, because a 403 on every asset
    of an app that otherwise deploys green is not something to discover from a
    browser.
    """
    if not served.exists():
        return
    try:
        subprocess.run(
            ["chmod", "-R", "a+rX", str(served)],
            check=True,
            capture_output=True,
            text=True,
        )
        log(f"Granted web server read access to {served}", level=3)
    except (subprocess.CalledProcessError, OSError) as e:
        log(
            f"Could not relax permissions on {served} for the web server: {e}. "
            f"Static files under it will be refused with 403.",
            level=1,
            fg="yellow",
        )
