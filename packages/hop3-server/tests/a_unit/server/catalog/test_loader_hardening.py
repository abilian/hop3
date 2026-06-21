# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for catalog loader XSS/path hardening (ADR 049 F6)."""

from __future__ import annotations

from hop3.server.catalog.loader import find_icon, load_app
from hop3.server.catalog.models import CatalogApp


def _app(catalog_dir, app_id, *, readme: str | None = None):
    d = catalog_dir / app_id
    d.mkdir(parents=True)
    (d / "hop3.toml").write_text(f'[metadata]\nid = "{app_id}"\ntitle = "{app_id}"\n')
    if readme is not None:
        (d / "readme.md").write_text(readme)
    return d


def test_readme_html_is_sanitized(tmp_path):
    malicious = (
        "# Title\n\n"
        "Normal **bold** text.\n\n"
        "<script>alert('xss')</script>\n\n"
        '<img src=x onerror="alert(1)">\n'
    )
    _app(tmp_path, "evil", readme=malicious)

    app = load_app(tmp_path / "evil")

    assert app is not None
    assert "<script" not in app.readme_html.lower()
    assert "onerror" not in app.readme_html.lower()
    assert "alert" not in app.readme_html.lower()
    # Safe formatting survives sanitization.
    assert "<strong>" in app.readme_html or "bold" in app.readme_html


def _catalog_app(source_path: str) -> CatalogApp:
    return CatalogApp(
        id="x",
        title="X",
        description="",
        version="",
        author="",
        website="",
        license="",
        source_path=source_path,
    )


def test_find_icon_returns_raster_icon(tmp_path):
    (tmp_path / "icon.webp").write_bytes(b"RIFFwebp")
    icon = find_icon(_catalog_app(str(tmp_path)))
    assert icon is not None
    assert icon.name == "icon.webp"


def test_find_icon_never_serves_svg(tmp_path):
    (tmp_path / "icon.svg").write_text("<svg onload='alert(1)'></svg>")
    assert find_icon(_catalog_app(str(tmp_path))) is None


def test_find_icon_no_source_path(tmp_path):
    assert find_icon(_catalog_app("")) is None


def test_find_icon_no_icon_file(tmp_path):
    assert find_icon(_catalog_app(str(tmp_path))) is None
