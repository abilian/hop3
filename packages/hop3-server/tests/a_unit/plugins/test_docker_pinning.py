# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Base-image pinning checks for the Docker builder.

A `FROM` naming a tag resolves to whatever that tag points at on the day of the
build, so the resulting image cannot be reproduced or audited. The builder
refuses rather than producing an image nobody can rebuild.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.plugins.docker.builder import unpinned_base_images

if TYPE_CHECKING:
    from pathlib import Path

DIGEST = "sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd"


def test_tag_only_base_image_is_unpinned():
    assert unpinned_base_images("FROM debian:trixie-slim\n") == ["debian:trixie-slim"]


def test_digest_pinned_base_image_passes():
    assert unpinned_base_images(f"FROM debian:trixie-slim@{DIGEST}\n") == []


def test_multi_stage_reports_each_unpinned_stage():
    dockerfile = f"FROM golang:1-trixie AS builder\nFROM debian:trixie-slim@{DIGEST}\n"
    assert unpinned_base_images(dockerfile) == ["golang:1-trixie"]


def test_reference_to_an_earlier_stage_is_not_a_base_image():
    """`FROM builder` names a stage built in this file, not a registry image."""
    dockerfile = f"FROM debian:trixie-slim@{DIGEST} AS builder\nFROM builder\n"
    assert unpinned_base_images(dockerfile) == []


def test_scratch_needs_no_digest():
    assert unpinned_base_images("FROM scratch\n") == []


def test_lowercase_from_and_as_are_handled():
    dockerfile = f"from debian:trixie-slim@{DIGEST} as build\nfrom build\n"
    assert unpinned_base_images(dockerfile) == []


def test_platform_flag_is_not_the_image():
    dockerfile = f"FROM --platform=$BUILDPLATFORM rust:1@{DIGEST} AS build\n"
    assert unpinned_base_images(dockerfile) == []
    assert unpinned_base_images("FROM --platform=linux/amd64 rust:1\n") == ["rust:1"]


def _offenders(dockerfiles: list[Path]) -> dict[str, list[str]]:
    # Fail rather than skip: a guard that quietly finds nothing to check is
    # indistinguishable from a guard that passes.
    assert dockerfiles, "no Dockerfiles found"
    return {
        str(df): bad
        for df in dockerfiles
        if (bad := unpinned_base_images(df.read_text()))
    }


def test_the_shipped_corpus_is_fully_pinned(catalog_apps):
    """Regression guard: every catalog Dockerfile still served stays pinned."""
    assert catalog_apps.is_dir(), f"app corpus not found at {catalog_apps}"
    dockerfiles = [
        df
        for df in catalog_apps.glob("*/*/Dockerfile")
        if df.parent.parent.name != "retired"
    ]
    assert _offenders(dockerfiles) == {}


def test_the_demos_and_fixtures_are_pinned(repo_root):
    """The demos deploy through the same builder; demo02 failed on a tag."""
    dockerfiles = [
        *repo_root.glob("demos/demo*/app/Dockerfile"),
        *repo_root.glob("apps/*/*/Dockerfile"),
    ]
    assert _offenders(dockerfiles) == {}
