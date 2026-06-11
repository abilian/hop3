# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the static deployer.

Regression focus: a static site served by nginx 403'd because the deploy
checkout left files mode 0600 (owner-only) and nginx workers run as www-data.
The deployer must relax the served tree to a+rX. See the demo03 failure:
`open(".../public/index.html") failed (13: Permission denied)`.
"""

from __future__ import annotations

import stat
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from hop3.plugins.deploy.static.deployer import StaticDeployer

if TYPE_CHECKING:
    from pathlib import Path


def _deployer(src_path: Path) -> StaticDeployer:
    """A StaticDeployer whose app.src_path is ``src_path`` (rest stubbed)."""
    ctx = MagicMock()
    ctx.app.src_path = src_path
    return StaticDeployer(context=ctx, artifact=MagicMock())


def _is_world_readable(p: Path) -> bool:
    return bool(p.stat().st_mode & stat.S_IROTH)


def test_grant_nginx_read_makes_files_world_readable(tmp_path: Path) -> None:
    public = tmp_path / "public"
    (public / "sub").mkdir(parents=True)
    index = public / "index.html"
    index.write_text("<h1>hi</h1>")
    nested = public / "sub" / "page.html"
    nested.write_text("nested")
    for f in (index, nested):
        f.chmod(0o600)
    (public / "sub").chmod(0o700)

    # Relative path resolves against app.src_path (mirrors the "static" worker).
    _deployer(tmp_path)._grant_nginx_read("public")

    assert _is_world_readable(index)
    assert _is_world_readable(nested)
    # Directories become traversable for the nginx worker...
    assert (public / "sub").stat().st_mode & stat.S_IXOTH
    # ...but data files are NOT made executable (a+rX, not a+rx).
    assert not (index.stat().st_mode & stat.S_IXOTH)


def test_grant_nginx_read_accepts_absolute_path(tmp_path: Path) -> None:
    index = tmp_path / "index.html"
    index.write_text("hi")
    index.chmod(0o600)

    # Absolute static_path is used as-is (src_path is irrelevant here).
    _deployer(tmp_path / "unused")._grant_nginx_read(str(tmp_path))

    assert _is_world_readable(index)


def test_grant_nginx_read_missing_path_is_noop(tmp_path: Path) -> None:
    # A non-existent served path must not raise (best-effort).
    _deployer(tmp_path)._grant_nginx_read(tmp_path / "does-not-exist")
