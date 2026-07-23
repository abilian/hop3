# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Per-OS-family translation of canonical (Debian) package names.

Apps declare `[build].packages` / `[run].packages` in hop3.toml using
**Debian package names** as the canonical form (this is the largest
ecosystem for PaaS hosts; every other distro maps from there). This
module converts those names to the per-OS equivalent at installer
time — see `baseline.py` for the calling context.

When a name is identical across distros (e.g. `ffmpeg`, `git`), the
table still lists it for each family so the lookup is uniform and
failures are explicit (missing from the table → `KeyError` →
installer refuses rather than guessing).

OS-family keys match the `detect_distro()` return values in
`hop3_installer.common`: `"debian"`, `"fedora"`.
"""

from __future__ import annotations

# Canonical package name (Debian) → { family: per-OS name or None }.
#
# `None` means "this package is not available on that family as a
# first-class name". Callers can treat None as "skip with warning" or
# "error", depending on policy. Today we skip + warn.
PACKAGE_ALIASES: dict[str, dict[str, str | None]] = {
    # --- Build tooling ---
    "build-essential": {"debian": "build-essential", "fedora": "gcc-c++"},
    "pkg-config": {"debian": "pkg-config", "fedora": "pkgconf-pkg-config"},
    "python3": {"debian": "python3", "fedora": "python3"},
    "python3-dev": {"debian": "python3-dev", "fedora": "python3-devel"},
    "nodejs": {"debian": "nodejs", "fedora": "nodejs"},
    # libnode-dev pulls Debian's bundled node headers + static libs
    # (libc-ares, libnghttp2, libicu, libbrotli from the same source).
    # Without it, npm-compiled native modules (isolated-vm, node-canvas)
    # fail link with "cannot find -lcares" etc. Fedora ships the
    # equivalents under nodejs-devel.
    "libnode-dev": {"debian": "libnode-dev", "fedora": "nodejs-devel"},
    # --- Dev headers / shared libraries ---
    "libbrotli-dev": {"debian": "libbrotli-dev", "fedora": "brotli-devel"},
    "libc-ares-dev": {"debian": "libc-ares-dev", "fedora": "c-ares-devel"},
    "libnghttp2-dev": {"debian": "libnghttp2-dev", "fedora": "libnghttp2-devel"},
    "libicu-dev": {"debian": "libicu-dev", "fedora": "libicu-devel"},
    "libssl-dev": {"debian": "libssl-dev", "fedora": "openssl-devel"},
    "libsqlite3-dev": {"debian": "libsqlite3-dev", "fedora": "sqlite-devel"},
    "libmariadb-dev": {
        "debian": "libmariadb-dev",
        "fedora": "mariadb-connector-c-devel",
    },
    "libpq-dev": {"debian": "libpq-dev", "fedora": "libpq-devel"},
    "libjpeg-dev": {"debian": "libjpeg-dev", "fedora": "libjpeg-devel"},
    "libpng-dev": {"debian": "libpng-dev", "fedora": "libpng-devel"},
    "libwebp-dev": {"debian": "libwebp-dev", "fedora": "libwebp-devel"},
    "libffi-dev": {"debian": "libffi-dev", "fedora": "libffi-devel"},
    # --- Runtime tools ---
    "ffmpeg": {"debian": "ffmpeg", "fedora": "ffmpeg"},
    "imagemagick": {"debian": "imagemagick", "fedora": "ImageMagick"},
    "poppler-utils": {"debian": "poppler-utils", "fedora": "poppler-utils"},
    # --- Database clients (runtime) ---
    "postgresql-client": {"debian": "postgresql-client", "fedora": "postgresql"},
    "mariadb-client": {"debian": "mariadb-client", "fedora": "mariadb"},
}


def translate(package: str, os_family: str) -> str | None:
    """
    Translate a canonical package name for the given OS family.

    Returns the per-OS name (same as canonical when no renaming is
    needed), or None when the package is not available on that family.
    Raises KeyError when the package is unknown (not in the table at
    all) — use `is_known()` first if you need to probe.
    """
    return PACKAGE_ALIASES[package][os_family]


def is_known(package: str) -> bool:
    """Whether `package` has a translation entry."""
    return package in PACKAGE_ALIASES


def supported_os_families() -> tuple[str, ...]:
    """OS families the translation table handles."""
    return ("debian", "fedora")
