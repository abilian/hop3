# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Realizing [[volumes]] (ADR 046 §2).

A persist volume must live outside `src/`, be linked into it, seed an empty
volume once (from what the app wrote there before, else from shipped content),
and survive the redeploy that wipes and re-extracts `src/`. A scratch volume is
linked the same way and reset whenever the tree is replaced.
"""

from __future__ import annotations

import inspect
import os
import shutil
import stat
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from hop3.deployers import deployer
from hop3.deployers.deployer import _reject_volumes_on_docker
from hop3.deployers.volumes import (
    drop_previous_source,
    previous_source_path,
    realize_volumes,
    retire_source_tree,
)

if TYPE_CHECKING:
    from pathlib import Path


def _app(tmp_path: Path) -> SimpleNamespace:
    app_path = tmp_path / "app"
    src = app_path / "src"
    src.mkdir(parents=True)
    return SimpleNamespace(
        app_path=app_path,
        src_path=src,
        volumes_path=app_path / "volumes",
        scratch_path=app_path / "scratch",
    )


def _persist(name: str, target: str, **extra) -> dict:
    return {"name": name, "target": target, "type": "persist", **extra}


def _scratch(name: str, target: str) -> dict:
    return {"name": name, "target": target, "type": "scratch"}


def _new_tree(app: SimpleNamespace, files: dict[str, str]) -> None:
    """What a deploy does to src/: set the old tree aside, extract a new one."""
    retire_source_tree(app)
    app.src_path.mkdir()
    for rel, text in files.items():
        path = app.src_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


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


# --- The tree a deploy replaces seeds the volumes it declares for the first time


def test_a_newly_declared_volume_keeps_what_the_app_wrote_there(tmp_path: Path) -> None:
    # Deployed without a volume, the app wrote its data into src/data. The
    # deploy that declares the volume must move that data in, not delete it
    # with the old tree.
    app = _app(tmp_path)
    (app.src_path / "data").mkdir()
    (app.src_path / "data" / "app.db").write_text("precious")

    _new_tree(app, {"data/.gitkeep": ""})
    realize_volumes(app, [_persist("data", "data")])
    drop_previous_source(app)

    assert (app.volumes_path / "data" / "app.db").read_text() == "precious"
    assert not (app.volumes_path / "data" / ".gitkeep").exists()
    assert (app.src_path / "data").is_symlink()
    assert not previous_source_path(app).exists()


def test_without_earlier_data_the_volume_is_seeded_from_the_new_tree(
    tmp_path: Path,
) -> None:
    app = _app(tmp_path)
    _new_tree(app, {"storage/seed.txt": "default"})
    realize_volumes(app, [_persist("store", "storage")])

    assert (app.volumes_path / "store" / "seed.txt").read_text() == "default"


def test_a_volume_with_data_is_not_seeded_again(tmp_path: Path) -> None:
    app = _app(tmp_path)
    vol = [_persist("data", "data")]
    realize_volumes(app, vol)
    (app.src_path / "data" / "kept.txt").write_text("kept")

    _new_tree(app, {"data/shipped.txt": "shipped"})
    realize_volumes(app, vol)

    assert sorted(p.name for p in (app.volumes_path / "data").iterdir()) == ["kept.txt"]


def test_a_link_in_the_replaced_tree_is_not_a_seed(tmp_path: Path) -> None:
    # src/data was already another volume's link: its storage is not ours.
    app = _app(tmp_path)
    other = tmp_path / "elsewhere"
    other.mkdir()
    (other / "secret").write_text("not yours")
    (app.src_path / "data").symlink_to(other)

    _new_tree(app, {})
    realize_volumes(app, [_persist("data", "data")])

    assert not any((app.volumes_path / "data").iterdir())
    assert (other / "secret").exists()


def test_a_seed_is_never_taken_through_a_link_out_of_the_tree(tmp_path: Path) -> None:
    # The app planted src/storage -> a directory outside the tree; the volume's
    # target is storage/app. Taking it would move files the app does not own.
    app = _app(tmp_path)
    outside = tmp_path / "outside"
    (outside / "app").mkdir(parents=True)
    (outside / "app" / "passwd").write_text("host file")
    (app.src_path / "storage").symlink_to(outside)

    _new_tree(app, {})
    realize_volumes(app, [_persist("files", "storage/app")])

    assert (outside / "app" / "passwd").read_text() == "host file"
    assert not any((app.volumes_path / "files").iterdir())


def test_a_failed_deploy_keeps_the_tree_the_app_last_ran_from(tmp_path: Path) -> None:
    # Deploy N set the running tree aside, then failed before its volumes were
    # realized. Deploy N+1 must seed from that tree, not from N's, which the
    # app never ran from.
    app = _app(tmp_path)
    (app.src_path / "data").mkdir()
    (app.src_path / "data" / "app.db").write_text("precious")

    _new_tree(app, {"data/.gitkeep": ""})  # deploy N fails after this
    _new_tree(app, {"data/.gitkeep": ""})  # deploy N+1
    realize_volumes(app, [_persist("data", "data")])

    assert (app.volumes_path / "data" / "app.db").read_text() == "precious"


def test_retire_on_a_first_deploy_is_a_noop(tmp_path: Path) -> None:
    app = _app(tmp_path)
    app.src_path.rmdir()
    retire_source_tree(app)
    assert not previous_source_path(app).exists()


# --- Scratch volumes


def test_scratch_is_linked_outside_src_and_seeded_from_the_tree(tmp_path: Path) -> None:
    app = _app(tmp_path)
    (app.src_path / "cache").mkdir()
    (app.src_path / "cache" / ".gitignore").write_text("*")

    realize_volumes(app, [_scratch("cache", "cache")])

    storage = app.scratch_path / "cache"
    assert (app.src_path / "cache").resolve() == storage.resolve()
    assert (storage / ".gitignore").read_text() == "*"


def test_scratch_is_reset_when_the_tree_is_replaced(tmp_path: Path) -> None:
    app = _app(tmp_path)
    vol = [_scratch("cache", "cache")]
    realize_volumes(app, vol)
    (app.src_path / "cache" / "compiled.php").write_text("stale")

    _new_tree(app, {"cache/.gitignore": "*"})
    realize_volumes(app, vol)

    storage = app.scratch_path / "cache"
    assert sorted(p.name for p in storage.iterdir()) == [".gitignore"]


def test_scratch_survives_a_deploy_that_keeps_the_tree(tmp_path: Path) -> None:
    # A config change redeploys without new source: the scratch holds the only
    # copy of what the source shipped there, so it must not be emptied.
    app = _app(tmp_path)
    (app.src_path / "lib").mkdir()
    (app.src_path / "lib" / "shipped.jar").write_text("needed")
    vol = [_scratch("lib", "lib")]

    realize_volumes(app, vol)
    realize_volumes(app, vol)

    assert (app.src_path / "lib" / "shipped.jar").read_text() == "needed"


def test_scratch_is_never_seeded_from_the_replaced_tree(tmp_path: Path) -> None:
    app = _app(tmp_path)
    (app.src_path / "cache").mkdir()
    (app.src_path / "cache" / "old-version.php").write_text("stale")

    _new_tree(app, {})
    realize_volumes(app, [_scratch("cache", "cache")])

    assert not any((app.scratch_path / "cache").iterdir())


# --- Linking after the build: what the build left at a target


def _unpack_over(app: SimpleNamespace, target: str, files: dict[str, str]) -> None:
    """What `tar x` does to a symlinked directory: replaces it with a real one."""
    link = app.src_path / target
    if link.is_symlink():
        link.unlink()
    for rel, text in files.items():
        path = link / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def test_a_link_the_build_replaced_is_put_back(tmp_path: Path) -> None:
    app = _app(tmp_path)
    vol = [_persist("storage", "storage")]
    realize_volumes(app, vol)
    (app.src_path / "storage" / "upload.png").write_text("user's")

    _new_tree(app, {})
    realize_volumes(app, vol)
    _unpack_over(app, "storage", {"framework/.gitignore": "*"})
    realize_volumes(app, vol)

    assert (app.src_path / "storage").is_symlink()
    assert (app.src_path / "storage" / "upload.png").read_text() == "user's"


def test_a_first_deploy_seeds_the_volume_from_what_the_build_produced(
    tmp_path: Path,
) -> None:
    # The recipe ships nothing at storage/; its build downloads the app, whose
    # archive carries the skeleton the app expects to find there.
    app = _app(tmp_path)
    _unpack_over(app, "storage", {"framework/views/.gitignore": "*"})
    realize_volumes(app, [_persist("storage", "storage")])

    skeleton = app.volumes_path / "storage" / "framework" / "views" / ".gitignore"
    assert skeleton.read_text() == "*"


def test_volumes_are_linked_once_after_the_build() -> None:
    """
    A build that moves the application into place breaks on a link in its way
    (LimeSurvey's `mv`, Keycloak's unpacked distribution). Link after it; keep
    the replaced tree until then, since seeding reads it.
    """
    assert "realize_volumes" not in inspect.getsource(
        deployer._prepare_source_for_build
    )
    source = inspect.getsource(deployer._do_deploy)
    linking = source.index("realize_volumes(app, app_config.hop3_config.volumes)")
    assert source.index('"postbuild"') < linking
    assert linking < source.index("drop_previous_source(app)")
    assert source.index("drop_previous_source(app)") < source.index("get_deployer(")


def test_a_volume_the_app_cannot_own_stops_the_deploy(
    tmp_path: Path, monkeypatch
) -> None:
    """It was logged, and the app started with a volume it could not write."""

    def chown_fails(*_a, **_kw):
        msg = "Operation not permitted"
        raise PermissionError(msg)

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(shutil, "chown", chown_fails)
    app = _app(tmp_path)

    with pytest.raises(ValueError, match="so the app could not write to it"):
        realize_volumes(app, [_persist("uploads", "data/uploads")])
