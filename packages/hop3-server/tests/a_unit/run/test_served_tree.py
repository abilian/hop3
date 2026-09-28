# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The web server reads the tree it serves, and the volumes linked into it.

``chmod -R`` does not follow links, so a volume beneath a document root kept
the owner-only modes of what it was seeded from, and nginx answered 403 on
every file in it. Only links into the app's own volume storage are followed:
an app can plant a link to anything.
"""

from __future__ import annotations

import stat
from typing import TYPE_CHECKING

from hop3.run.served_tree import grant_web_server_read

if TYPE_CHECKING:
    from pathlib import Path


def _world_readable(path: Path) -> bool:
    return bool(path.stat().st_mode & stat.S_IROTH)


def _owner_only(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(0o600)
    return path


def test_the_served_tree_becomes_readable(tmp_path: Path) -> None:
    css = _owner_only(tmp_path / "public" / "app.css", "body{}")
    grant_web_server_read(tmp_path / "public")
    assert _world_readable(css)


def test_a_volume_linked_beneath_it_is_granted_too(tmp_path: Path) -> None:
    volumes = tmp_path / "volumes"
    theme = _owner_only(volumes / "themes" / "style.css", "body{}")
    public = tmp_path / "src"
    public.mkdir()
    (public / "themes").symlink_to(volumes / "themes")

    grant_web_server_read(public, (volumes,))

    assert _world_readable(theme)


def test_a_link_out_of_the_volume_storage_is_not_followed(tmp_path: Path) -> None:
    secret = _owner_only(tmp_path / "home" / "hop3.db", "tokens")
    public = tmp_path / "src"
    public.mkdir()
    (public / "planted").symlink_to(secret.parent)

    grant_web_server_read(public, (tmp_path / "volumes",))

    assert not _world_readable(secret)
