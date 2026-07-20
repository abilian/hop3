# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Base-image pinning checks for the Docker builder.

A `FROM` naming a tag resolves to whatever that tag points at on the day of the
build, so the resulting image cannot be reproduced or audited. The builder
refuses rather than producing an image nobody can rebuild.
"""

from __future__ import annotations

from pathlib import Path

from hop3.plugins.docker.builder import unpinned_base_images

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


def test_the_shipped_corpus_is_fully_pinned():
    """Regression guard: every Dockerfile in the docker variant stays pinned."""
    root = Path(__file__).parents[5] / "apps" / "real-apps-docker"
    # Fail rather than skip: a guard that quietly finds nothing to check is
    # indistinguishable from a guard that passes.
    assert root.is_dir(), f"app corpus not found at {root}"
    dockerfiles = list(root.glob("*/Dockerfile"))
    assert dockerfiles, f"no Dockerfiles under {root}"
    offenders = {
        df.parent.name: bad
        for df in dockerfiles
        if (bad := unpinned_base_images(df.read_text()))
    }
    assert offenders == {}, f"unpinned base images: {offenders}"
