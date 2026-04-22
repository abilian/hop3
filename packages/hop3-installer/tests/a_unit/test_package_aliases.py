# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the per-OS package-alias translation table."""

from __future__ import annotations

import pytest
from hop3_installer.server_installer.package_aliases import (
    PACKAGE_ALIASES,
    is_known,
    supported_os_families,
    translate,
)


class TestTranslate:
    def test_identity_translation_when_name_matches(self):
        assert translate("ffmpeg", "debian") == "ffmpeg"
        assert translate("ffmpeg", "fedora") == "ffmpeg"

    def test_renamed_dev_packages(self):
        assert translate("libbrotli-dev", "debian") == "libbrotli-dev"
        assert translate("libbrotli-dev", "fedora") == "brotli-devel"

    def test_unknown_package_raises(self):
        with pytest.raises(KeyError):
            translate("some-obscure-package-no-one-declares", "debian")

    def test_unknown_os_family_raises(self):
        with pytest.raises(KeyError):
            translate("ffmpeg", "gentoo")


class TestIsKnown:
    def test_true_for_table_entry(self):
        assert is_known("libbrotli-dev")
        assert is_known("ffmpeg")

    def test_false_for_unknown_entry(self):
        assert not is_known("random-thing-42")


class TestTableCoverage:
    """All entries must cover every supported OS family — incomplete
    rows would silently drop a package on some hosts."""

    def test_every_entry_covers_every_family(self):
        families = set(supported_os_families())
        for pkg, translations in PACKAGE_ALIASES.items():
            missing = families - translations.keys()
            assert not missing, (
                f"{pkg} is missing translations for {missing}; "
                "every entry must cover every supported OS family"
            )

    def test_supported_families_nonempty(self):
        assert len(supported_os_families()) > 0

    def test_packages_declared_by_current_catalogue_are_in_table(self):
        """directus + owncast are the only apps declaring
        [build].packages today. Those declarations must be in the
        table or the installer can't translate them on Fedora."""
        expected = {
            "libbrotli-dev",
            "build-essential",
            "python3",
            "pkg-config",
            "ffmpeg",
        }
        missing = expected - PACKAGE_ALIASES.keys()
        assert not missing, f"Catalogue declarations not in table: {missing}"
