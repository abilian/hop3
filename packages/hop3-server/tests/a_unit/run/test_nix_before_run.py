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

from hop3.plugins.build.nix import builder
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
