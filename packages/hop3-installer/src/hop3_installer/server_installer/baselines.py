# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Catalogue-derived installer baselines, per OS family.

GENERATED FROM apps/*/hop3.toml by
`python -m hop3_installer.server_installer.baseline`.
Do not edit by hand. Regenerate after catalogue changes.
"""

from __future__ import annotations

BASELINE_PACKAGES: dict[str, list[str]] = {
    "debian": [
        "build-essential",
        "ffmpeg",
        "libbrotli-dev",
        "libc-ares-dev",
        "libicu-dev",
        "libnghttp2-dev",
        "libnode-dev",
        "pkg-config",
        "python3",
    ],
    "fedora": [
        "brotli-devel",
        "c-ares-devel",
        "ffmpeg",
        "gcc-c++",
        "libicu-devel",
        "libnghttp2-devel",
        "nodejs-devel",
        "pkgconf-pkg-config",
        "python3",
    ],
}
