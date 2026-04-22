# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the installer baseline-derivation library.

Uses a synthetic apps/ tree under tmp_path so the tests don't depend
on what the real catalogue happens to declare today — that coupling
would make test updates a chore every time a new app is added.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3_installer.server_installer.baseline import (
    BaselineSource,
    derive_baseline,
    format_baselines_module,
)

if TYPE_CHECKING:
    from pathlib import Path


def _write_hop3_toml(
    app_dir: Path, *, build: list[str] | None = None, run: list[str] | None = None
) -> None:
    """Shape the minimal hop3.toml a declaration audit cares about."""
    app_dir.mkdir(parents=True, exist_ok=True)
    lines = ["[metadata]", f'id = "{app_dir.name}"', "", "[build]"]
    lines.append('builder = "local"')
    if build:
        packages = ", ".join(f'"{p}"' for p in build)
        lines.append(f"packages = [{packages}]")
    if run:
        lines.append("")
        lines.append("[run]")
        packages = ", ".join(f'"{p}"' for p in run)
        lines.append(f"packages = [{packages}]")
    (app_dir / "hop3.toml").write_text("\n".join(lines) + "\n")


class TestDeriveBaseline:
    def test_empty_catalogue_yields_empty_baseline(self, tmp_path):
        result = derive_baseline([tmp_path])
        assert result.canonical == ()
        assert result.sources == ()
        # Per-OS lists exist for every supported family, all empty.
        assert set(result.by_os_family.keys()) >= {"debian", "fedora"}
        assert all(v == () for v in result.by_os_family.values())

    def test_declarations_unioned_and_deduped(self, tmp_path):
        _write_hop3_toml(tmp_path / "a", build=["libbrotli-dev", "ffmpeg"])
        _write_hop3_toml(tmp_path / "b", build=["ffmpeg"], run=["poppler-utils"])
        result = derive_baseline([tmp_path])
        assert result.canonical == ("ffmpeg", "libbrotli-dev", "poppler-utils")

    def test_translation_applied_per_family(self, tmp_path):
        _write_hop3_toml(tmp_path / "a", build=["libbrotli-dev"])
        result = derive_baseline([tmp_path])
        assert result.by_os_family["debian"] == ("libbrotli-dev",)
        assert result.by_os_family["fedora"] == ("brotli-devel",)

    def test_sources_record_provenance(self, tmp_path):
        _write_hop3_toml(tmp_path / "myapp", build=["ffmpeg"], run=["poppler-utils"])
        result = derive_baseline([tmp_path])
        assert (
            BaselineSource(package="ffmpeg", app="myapp", field="build")
            in result.sources
        )
        assert (
            BaselineSource(package="poppler-utils", app="myapp", field="run")
            in result.sources
        )

    def test_unknown_package_surfaced_without_crashing(self, tmp_path):
        _write_hop3_toml(tmp_path / "a", build=["a-package-not-in-the-table"])
        result = derive_baseline([tmp_path])
        # Canonical list still includes it (for human review).
        assert "a-package-not-in-the-table" in result.canonical
        # Per-family translations drop it cleanly.
        assert "a-package-not-in-the-table" not in result.by_os_family["debian"]
        # CI signal.
        assert "a-package-not-in-the-table" in result.unknown

    def test_malformed_toml_skipped_quietly(self, tmp_path):
        (tmp_path / "broken").mkdir()
        (tmp_path / "broken" / "hop3.toml").write_text("[build\npackages = [\n")
        _write_hop3_toml(tmp_path / "ok", build=["ffmpeg"])
        result = derive_baseline([tmp_path])
        # The good app still contributed.
        assert result.canonical == ("ffmpeg",)

    def test_nonstring_package_entries_ignored(self, tmp_path):
        _write_hop3_toml(tmp_path / "ok", build=["ffmpeg"])
        # Hand-craft a TOML with a non-string entry.
        (tmp_path / "weird" / "hop3.toml").parent.mkdir()
        (tmp_path / "weird" / "hop3.toml").write_text(
            '[metadata]\nid = "weird"\n\n[build]\npackages = ["libbrotli-dev", 42]\n'
        )
        result = derive_baseline([tmp_path])
        # 42 is silently dropped; string entry survives.
        assert "libbrotli-dev" in result.canonical
        assert 42 not in result.canonical


class TestFormatBaselinesModule:
    def test_emits_valid_python_module(self, tmp_path):
        _write_hop3_toml(tmp_path / "a", build=["ffmpeg", "libbrotli-dev"])
        result = derive_baseline([tmp_path])
        text = format_baselines_module(result)

        namespace: dict = {}
        exec(compile(text, "<generated>", "exec"), namespace)
        assert "BASELINE_PACKAGES" in namespace
        bp = namespace["BASELINE_PACKAGES"]
        assert set(bp.keys()) >= {"debian", "fedora"}
        assert bp["debian"] == list(result.by_os_family["debian"])

    def test_contains_generated_warning_header(self, tmp_path):
        result = derive_baseline([tmp_path])
        text = format_baselines_module(result)
        assert "GENERATED FROM" in text
        assert "Do not edit by hand" in text

    def test_license_header_present(self, tmp_path):
        result = derive_baseline([tmp_path])
        text = format_baselines_module(result)
        assert "SPDX-License-Identifier" in text
