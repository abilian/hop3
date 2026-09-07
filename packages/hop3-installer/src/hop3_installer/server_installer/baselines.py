# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Catalogue-derived installer baselines, per OS family.

GENERATED FROM the catalog's apps/<status>/*/hop3.toml by
`python -m hop3_installer.server_installer.baseline`.
Do not edit by hand. Regenerate after catalogue changes.
"""

from __future__ import annotations

BASELINE_PACKAGES: dict[str, list[str]] = {
    "debian": [
        "build-essential",
        "ffmpeg",
        "fonts-liberation",
        "ghostscript",
        "gnupg",
        "icc-profiles-free",
        "imagemagick",
        "libbrotli-dev",
        "libc-ares-dev",
        "libicu-dev",
        "libmagic1",
        "libmariadb-dev",
        "libnghttp2-dev",
        "libpq-dev",
        "libpq5",
        "libzbar0",
        "pkg-config",
        "pngquant",
        "poppler-utils",
        "python3",
        "python3-dev",
        "qpdf",
        "tesseract-ocr",
        "tesseract-ocr-eng",
        "unpaper",
    ],
    "fedora": [
        "ImageMagick",
        "brotli-devel",
        "c-ares-devel",
        "ffmpeg",
        "file-libs",
        "gcc-c++",
        "ghostscript",
        "gnupg2",
        "icc-profiles-openicc",
        "liberation-fonts",
        "libicu-devel",
        "libnghttp2-devel",
        "libpq",
        "libpq-devel",
        "mariadb-connector-c-devel",
        "pkgconf-pkg-config",
        "pngquant",
        "poppler-utils",
        "python3",
        "python3-devel",
        "qpdf",
        "tesseract",
        "tesseract-langpack-eng",
        "unpaper",
        "zbar",
    ],
}
