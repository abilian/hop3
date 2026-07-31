# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
A Nix app must be able to run a first-run bootstrap.

Every native recipe has one — write the config, install the schema, create the
admin — and it lives in `[run] before-run`. For a Nix app that hook was
unusable: the artifact reported the read-only store path as its working
directory, so a bootstrap script was neither found nor able to write. The whole
Nix corpus went without one, and 12 of its apps deploy a running-but-uninstalled
application as a result.
"""

from __future__ import annotations

import inspect
import os
from types import SimpleNamespace

import pytest

from hop3.plugins.build.nix import builder
from hop3.plugins.build.nix.gen.templates import php_app
from hop3.run.spawn import AppLauncher


def test_a_nix_artifact_points_before_run_at_the_writable_app_dir() -> None:
    """
    The Nix builder must not hand back the store path as `working_dir`.

    `run/spawn.py` uses `artifact.runtime.working_dir` as the cwd for every
    before-run command. The store is read-only, so any bootstrap there fails on
    its first write — if it is found at all, which it is not, because recipe
    scripts live in the app's source directory.
    """
    source = inspect.getsource(builder)
    assert "working_dir=str(self.context.source_path)" in source, (
        "the Nix builder must report the app's own directory"
    )
    assert "working_dir=store_path" not in source, (
        "the read-only store path must not be the before-run cwd"
    )


def test_before_run_receives_a_fully_resolved_environment() -> None:
    """
    PORT and the artifact's PATH are settled BEFORE before-run, not after.

    A bootstrap that writes a config file interpolates ${PORT}; one that calls
    the app's CLI needs the artifact's `path_prepend`. Both come from
    `make_env()`, which runs in `__post_init__` — so by the time
    `_run_before_run_commands` is reached, `self.env` is complete. This test
    pins that ordering: moving the port block out of `make_env`, or calling
    before-run earlier, would hand bootstrap scripts an empty PORT and a PATH
    without the app on it, silently.
    """
    post_init = inspect.getsource(AppLauncher.__post_init__)
    assert "self.env = self.make_env()" in post_init

    make_env = inspect.getsource(AppLauncher.make_env)
    assert '"PORT" not in env' in make_env, "port resolution must live in make_env"
    assert "_apply_artifact_runtime" in make_env, "artifact PATH must be applied there"

    # before-run is handed the prepared environment, not a fresh one.
    spawn = inspect.getsource(AppLauncher.spawn_app)
    assert "_run_before_run_commands(env)" in spawn


def _launcher(tmp_path, writable_tree: str):
    """An AppLauncher with just enough shape to exercise materialisation."""
    src = tmp_path / "src"
    src.mkdir()
    launcher = AppLauncher.__new__(AppLauncher)
    launcher.app = SimpleNamespace(src_path=src, name="myapp")
    launcher.app_name = "myapp"
    launcher.artifact = SimpleNamespace(
        runtime=SimpleNamespace(writable_tree=writable_tree)
    )
    return launcher, src


class TestWritableTree:
    """
    A read-only build tree must be in place BEFORE the app's bootstrap runs.

    This copy used to be a line in the generated wrapper, which runs when the
    app starts — after `[run] before-run`. So a bootstrap ran against a
    directory holding the recipe and none of the application, and Matomo's
    installer died on `Failed opening required core/bootstrap.php` on a build
    that was otherwise correct.
    """

    def test_the_tree_is_copied_into_the_app_directory(self, tmp_path) -> None:
        store = tmp_path / "store"
        (store / "core").mkdir(parents=True)
        (store / "core" / "bootstrap.php").write_text("<?php")
        launcher, src = _launcher(tmp_path, str(store))

        launcher._materialize_writable_tree()

        assert (src / "core" / "bootstrap.php").read_text() == "<?php"

    def test_a_second_deploy_does_not_overwrite_what_the_app_wrote(
        self, tmp_path
    ) -> None:
        """
        The marker exists for this: copying again reverts live configuration.

        A PHP app writes its own config into its install directory. Re-copying
        the pristine tree over it on the next deploy would silently undo that.
        """
        store = tmp_path / "store"
        store.mkdir()
        (store / "config.php").write_text("pristine")
        launcher, src = _launcher(tmp_path, str(store))

        launcher._materialize_writable_tree()
        (src / "config.php").write_text("configured by the bootstrap")
        launcher._materialize_writable_tree()

        assert (src / "config.php").read_text() == "configured by the bootstrap"

    def test_a_missing_tree_is_loud(self, tmp_path) -> None:
        """Without the tree the app has no code; failing quietly hides that."""
        launcher, _ = _launcher(tmp_path, str(tmp_path / "gone"))

        with pytest.raises(RuntimeError, match="does not exist"):
            launcher._materialize_writable_tree()

    def test_an_app_without_one_is_untouched(self, tmp_path) -> None:
        launcher, src = _launcher(tmp_path, "")

        launcher._materialize_writable_tree()

        assert list(src.iterdir()) == []


def test_materialization_runs_before_the_bootstrap() -> None:
    """Ordering is the entire point of the change; pin it."""
    spawn = inspect.getsource(AppLauncher.spawn_app)
    assert spawn.index("_materialize_writable_tree") < spawn.index(
        "_run_before_run_commands"
    )


def test_the_app_directory_itself_ends_up_writable(tmp_path) -> None:
    """
    copytree preserves mode — including on the destination.

    A Nix store tree is 0555, so the copy left the app's own directory
    read-only. Nothing could be written into it and the next deploy's teardown
    failed with "Permission denied", stranding the app on disk.
    """
    store = tmp_path / "store"
    (store / "sub").mkdir(parents=True)
    (store / "sub" / "f.php").write_text("x")
    for path in [store, store / "sub", store / "sub" / "f.php"]:
        path.chmod(0o555 if path.is_dir() else 0o444)

    launcher, src = _launcher(tmp_path, str(store))
    launcher._materialize_writable_tree()

    assert os.access(src, os.W_OK), "the app directory must be writable"
    assert os.access(src / "sub", os.W_OK)
    assert os.access(src / "sub" / "f.php", os.W_OK)
    (src / "new.php").write_text("the bootstrap can write here")


def test_php_app_names_the_application_subdirectory(tmp_path) -> None:
    """
    `$out/app`, not `$out`.

    `$out` also holds the generated wrapper and hop3/runtime.json. Copying it
    wholesale puts the application one directory down from where it expects to
    be, and leaves build metadata in the app directory for the next deploy to
    trip over — which is exactly what happened: `hop3.nix` reappeared and the
    builder refused with "Both hop3.nix and a [nix].template section".
    """
    source = inspect.getsource(php_app)
    assert '"writable_tree": "$out/app"' in source
    assert '"writable_tree": "$out"' not in source
