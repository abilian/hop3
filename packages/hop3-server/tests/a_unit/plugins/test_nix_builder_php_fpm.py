# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
A Nix-built PHP app is served by php-fpm, as a native one is.

The expression names what it built (runtime.json's ``php_fpm``); the builder
turns that into the same pool, worker and document root the PHP toolchain
produces, so the spawn path, the proxy and the readiness gate need nothing
Nix-specific.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from hop3.core.protocols import BuildContext
from hop3.plugins.build.nix import builder as builder_module
from hop3.plugins.build.nix.builder import NixBuilder
from hop3.toolchains.php_fpm import POOL_TEMPLATE_NAME

if TYPE_CHECKING:
    from pathlib import Path


def _store(tmp_path: Path, runtime: dict, *, front_controller: str) -> Path:
    """A fake build output: php-fpm, the application tree, runtime.json."""
    store = tmp_path / "store" / "abc-app"
    (store / "bin").mkdir(parents=True)
    (store / "bin" / "php-fpm").write_text("#!/bin/sh\n")
    root = store / "app" / front_controller
    root.mkdir(parents=True)
    (root / "index.php").write_text("<?php\n")
    (store / "hop3").mkdir()
    text = json.dumps(runtime).replace("$out", str(store))
    (store / "hop3" / "runtime.json").write_text(text)
    return store


def _build(tmp_path: Path, monkeypatch, store: Path):
    src = tmp_path / "apps" / "shop" / "src"
    src.mkdir(parents=True)
    (src / "hop3.nix").write_text("# explicit")
    monkeypatch.setattr(builder_module, "APP_ROOT", tmp_path / "apps")
    monkeypatch.setattr(NixBuilder, "_kill_stale_nix_builds", lambda self, f: None)
    monkeypatch.setattr(NixBuilder, "_nix_build", lambda self, f: str(store))
    context = BuildContext(app_name="shop", source_path=src, app_config={})
    return NixBuilder(context).build(), src


def _fpm(**entry: str) -> dict:
    return {
        "php_fpm": {"binary": "$out/bin/php-fpm", "tree": "$out/app", **entry},
        "workers": {},
        "env": {"APP_ENV": "prod"},
        "path": ["$out/bin"],
    }


def test_writable_tree_is_served_from_the_source_directory(tmp_path, monkeypatch):
    runtime = {**_fpm(document_root="htdocs"), "writable_tree": "$out/app"}
    store = _store(tmp_path, runtime, front_controller="htdocs")

    artifact, src = _build(tmp_path, monkeypatch, store)

    assert artifact.runtime.backend_protocol == "fastcgi"
    web = artifact.runtime.workers["web"]
    assert web.startswith(f"{store}/bin/php-fpm --nodaemonize --fpm-config ")
    # The deploy copies the tree into src/ after this build: that copy is
    # what the proxy serves, not the read-only store.
    assert artifact.runtime.env_vars["PHP_DOCUMENT_ROOT"] == str(src / "htdocs")
    assert artifact.runtime.env_vars["APP_ENV"] == "prod"
    assert (tmp_path / "apps" / "shop" / POOL_TEMPLATE_NAME).is_file()


def test_front_controller_is_detected_in_a_store_tree(tmp_path, monkeypatch):
    store = _store(tmp_path, _fpm(), front_controller="public")

    artifact, _ = _build(tmp_path, monkeypatch, store)

    root = artifact.runtime.env_vars["PHP_DOCUMENT_ROOT"]
    assert root == str((store / "app" / "public").resolve())


def test_a_missing_php_fpm_fails_the_build(tmp_path, monkeypatch):
    store = _store(tmp_path, _fpm(), front_controller="")
    (store / "bin" / "php-fpm").unlink()

    with pytest.raises(RuntimeError, match="php-fpm"):
        _build(tmp_path, monkeypatch, store)


def test_a_declared_root_the_tree_lacks_fails_the_build(tmp_path, monkeypatch):
    store = _store(tmp_path, _fpm(document_root="web"), front_controller="")

    with pytest.raises(RuntimeError, match="app/web"):
        _build(tmp_path, monkeypatch, store)
