# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Realizing [[volumes]] persistence (ADR 046 §2).

A persist volume must live outside `src/`, be linked into it, seed an empty
volume from shipped content once, and survive the redeploy that
wipes and re-extracts `src/`.
"""

from __future__ import annotations

import os
import shutil
import stat
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from hop3.deployers.deployer import _reject_volumes_on_docker
from hop3.deployers.volumes import realize_volumes

if TYPE_CHECKING:
    from pathlib import Path


def _app(tmp_path: Path) -> SimpleNamespace:
    app_path = tmp_path / "app"
    src = app_path / "src"
    src.mkdir(parents=True)
    return SimpleNamespace(
        app_path=app_path, src_path=src, volumes_path=app_path / "volumes"
    )


def _persist(name: str, target: str, **extra) -> dict:
    return {"name": name, "target": target, "type": "persist", **extra}


def test_links_target_to_persistent_dir(tmp_path: Path) -> None:
    app = _app(tmp_path)
    realize_volumes(app, [_persist("uploads", "data/uploads")])

    link = app.src_path / "data" / "uploads"
    volume_dir = app.app_path / "volumes" / "uploads"
    assert link.is_symlink()
    assert link.resolve() == volume_dir.resolve()
    assert volume_dir.is_dir()
    # The link is writable and writes land in the persistent dir.
    (link / "f.txt").write_text("hi")
    assert (volume_dir / "f.txt").read_text() == "hi"


def test_seeds_empty_volume_from_shipped_content_once(tmp_path: Path) -> None:
    app = _app(tmp_path)
    shipped = app.src_path / "storage"
    shipped.mkdir()
    (shipped / "seed.txt").write_text("default")

    realize_volumes(app, [_persist("store", "storage")])

    volume_dir = app.app_path / "volumes" / "store"
    assert (volume_dir / "seed.txt").read_text() == "default"  # seeded
    assert (app.src_path / "storage").is_symlink()


def test_survives_a_redeploy(tmp_path: Path) -> None:
    app = _app(tmp_path)
    vol = [_persist("store", "storage")]

    realize_volumes(app, vol)
    (app.src_path / "storage" / "user-data.txt").write_text("precious")

    # Simulate a redeploy: src/ is wiped and re-extracted (with shipped content),
    # destroying the symlink but NOT the volume dir (which lives under app_path).
    shutil.rmtree(app.src_path)
    app.src_path.mkdir()
    shipped = app.src_path / "storage"
    shipped.mkdir()
    (shipped / "seed.txt").write_text("default-from-image")

    realize_volumes(app, vol)

    link = app.src_path / "storage"
    assert link.is_symlink()
    assert (link / "user-data.txt").read_text() == "precious"  # survived
    # Volume already had data, so shipped content did NOT overwrite it.
    assert not (link / "seed.txt").exists()


def test_is_idempotent_when_already_linked(tmp_path: Path) -> None:
    app = _app(tmp_path)
    vol = [_persist("uploads", "data/uploads")]
    realize_volumes(app, vol)
    (app.src_path / "data" / "uploads" / "keep.txt").write_text("x")

    realize_volumes(app, vol)  # second call: link already correct

    assert (app.src_path / "data" / "uploads" / "keep.txt").read_text() == "x"


def test_tmpfs_and_bind_fail_loud(tmp_path: Path) -> None:
    app = _app(tmp_path)
    with pytest.raises(ValueError, match="not implemented"):
        realize_volumes(app, [{"name": "c", "target": "cache", "type": "tmpfs"}])
    with pytest.raises(ValueError, match="not implemented"):
        realize_volumes(app, [{"name": "h", "target": "host", "type": "bind"}])


def test_file_at_target_fails_loud(tmp_path: Path) -> None:
    app = _app(tmp_path)
    (app.src_path / "data").write_text("i am a file, not a dir")
    with pytest.raises(ValueError, match="must be directories"):
        realize_volumes(app, [_persist("d", "data")])


def test_empty_volumes_is_a_noop(tmp_path: Path) -> None:
    app = _app(tmp_path)
    realize_volumes(app, [])
    assert not (app.app_path / "volumes").exists()


def test_honors_mode(tmp_path: Path) -> None:
    app = _app(tmp_path)
    realize_volumes(app, [_persist("locked", "data/locked", mode="0700")])
    vol_dir = app.volumes_path / "locked"
    assert stat.S_IMODE(vol_dir.stat().st_mode) == 0o700


def test_symlink_is_relative(tmp_path: Path) -> None:
    # No absolute host path may leak into src/ (it would break backup/restore
    # and any copied tree), but the link must still resolve at runtime.
    app = _app(tmp_path)
    realize_volumes(app, [_persist("uploads", "data/uploads")])
    link = app.src_path / "data" / "uploads"
    assert not os.path.isabs(os.readlink(link))
    assert link.resolve() == (app.volumes_path / "uploads").resolve()


def test_docker_builder_with_volumes_aborts() -> None:
    with pytest.raises(ValueError, match="not yet supported for Docker"):
        _reject_volumes_on_docker("docker", [{"name": "x", "target": "data"}])


def test_docker_builder_without_volumes_is_ok() -> None:
    _reject_volumes_on_docker("docker", [])  # must not raise


def test_native_builder_with_volumes_is_ok() -> None:
    _reject_volumes_on_docker("local", [{"name": "x", "target": "data"}])  # no raise
