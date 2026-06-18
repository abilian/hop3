# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for CatalogApp memory parsing + resource tier."""

from __future__ import annotations

import pytest

from hop3.server.catalog.models import CatalogApp


def _app(memory: str | None) -> CatalogApp:
    return CatalogApp(
        id="x",
        title="X",
        description="",
        version="",
        author="",
        website="",
        license="",
        memory=memory,
    )


@pytest.mark.parametrize(
    ("memory", "mb"),
    [
        ("256MB", 256),
        ("512MB", 512),
        ("1GB", 1024),
        ("2GB", 2048),
        ("1G", 1024),
        ("512M", 512),
        ("2g", 2048),  # lowercase
        ("1.5GB", 1536),  # decimal
        ("1 GB", 1024),  # embedded space
        ("1024", 1024),  # bare number is MB
        (None, None),
        ("", None),
        ("lots", None),  # unparseable -> None, never raises (regression: '1GB' crash)
    ],
)
def test_memory_mb(memory, mb):
    assert _app(memory).memory_mb == mb


@pytest.mark.parametrize(
    ("memory", "tier"),
    [
        ("256MB", "light"),
        ("512MB", "medium"),
        ("1GB", "heavy"),
        (None, "medium"),  # unknown -> default
        ("garbage", "medium"),  # unparseable -> default, no crash
    ],
)
def test_compute_resource_tier(memory, tier):
    assert _app(memory).compute_resource_tier() == tier
