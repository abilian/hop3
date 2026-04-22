# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the LocalBuilder declared-package probe."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.core.protocols import BuildContext
from hop3.plugins.build.local_build import builder as builder_module

if TYPE_CHECKING:
    from pathlib import Path


def _ctx(tmp_path: Path, app_config: dict) -> BuildContext:
    src = tmp_path / "src"
    src.mkdir()
    return BuildContext(app_name="myapp", source_path=src, app_config=app_config)


def test_probe_returns_empty_when_no_declarations(tmp_path, monkeypatch):
    monkeypatch.setattr(builder_module.shutil, "which", lambda _: "/usr/bin/dpkg")
    ctx = _ctx(tmp_path, app_config={"hop3_config": {}})
    assert builder_module._probe_declared_packages(ctx) == []


def test_probe_returns_empty_when_no_package_manager(tmp_path, monkeypatch):
    """No dpkg/rpm → unknown system → no probe."""
    monkeypatch.setattr(builder_module.shutil, "which", lambda _: None)
    ctx = _ctx(
        tmp_path,
        app_config={
            "hop3_config": {"build": {"packages": ["libbrotli-dev"]}},
        },
    )
    assert builder_module._probe_declared_packages(ctx) == []


def test_probe_surfaces_missing_dpkg_packages(tmp_path, monkeypatch):
    monkeypatch.setattr(
        builder_module.shutil,
        "which",
        lambda name: "/usr/bin/dpkg" if name == "dpkg" else None,
    )
    # Pretend libbrotli-dev is missing, build-essential is installed.
    monkeypatch.setattr(
        builder_module,
        "_is_installed_dpkg",
        lambda pkg: pkg == "build-essential",
    )
    ctx = _ctx(
        tmp_path,
        app_config={
            "hop3_config": {
                "build": {"packages": ["libbrotli-dev", "build-essential"]}
            },
        },
    )
    assert builder_module._probe_declared_packages(ctx) == ["libbrotli-dev"]


def test_probe_combines_build_and_run_declarations(tmp_path, monkeypatch):
    monkeypatch.setattr(
        builder_module.shutil,
        "which",
        lambda name: "/usr/bin/dpkg" if name == "dpkg" else None,
    )
    monkeypatch.setattr(builder_module, "_is_installed_dpkg", lambda _: False)
    ctx = _ctx(
        tmp_path,
        app_config={
            "hop3_config": {
                "build": {"packages": ["libbrotli-dev"]},
                "run": {"packages": ["ffmpeg"]},
            },
        },
    )
    missing = builder_module._probe_declared_packages(ctx)
    assert set(missing) == {"libbrotli-dev", "ffmpeg"}


def test_probe_prefers_dpkg_over_rpm(tmp_path, monkeypatch):
    """Both dpkg and rpm would be weird, but dpkg wins (Debian-first)."""
    monkeypatch.setattr(builder_module.shutil, "which", lambda _: "/usr/bin/dpkg")
    called = {"dpkg": 0, "rpm": 0}

    def fake_dpkg(_p):
        called["dpkg"] += 1
        return True

    def fake_rpm(_p):
        called["rpm"] += 1
        return True

    monkeypatch.setattr(builder_module, "_is_installed_dpkg", fake_dpkg)
    monkeypatch.setattr(builder_module, "_is_installed_rpm", fake_rpm)

    ctx = _ctx(
        tmp_path,
        app_config={"hop3_config": {"build": {"packages": ["libbrotli-dev"]}}},
    )
    builder_module._probe_declared_packages(ctx)
    assert called == {"dpkg": 1, "rpm": 0}


def test_probe_handles_malformed_hop3_config(tmp_path, monkeypatch):
    """Non-dict hop3_config (shouldn't happen but might) → empty list."""
    monkeypatch.setattr(builder_module.shutil, "which", lambda _: "/usr/bin/dpkg")
    ctx = _ctx(tmp_path, app_config={"hop3_config": "not a dict"})
    assert builder_module._probe_declared_packages(ctx) == []


def test_probe_ignores_non_string_package_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(
        builder_module.shutil,
        "which",
        lambda name: "/usr/bin/dpkg" if name == "dpkg" else None,
    )
    monkeypatch.setattr(builder_module, "_is_installed_dpkg", lambda _: False)
    ctx = _ctx(
        tmp_path,
        app_config={
            "hop3_config": {
                "build": {"packages": ["libbrotli-dev", 42, None]},
            },
        },
    )
    assert builder_module._probe_declared_packages(ctx) == ["libbrotli-dev"]
