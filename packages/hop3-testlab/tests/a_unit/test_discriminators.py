# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Variant/app discriminators derived from a test's path-based name."""

from __future__ import annotations

import pytest

from hop3_testlab.discriminators import short_app, variant_of


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("apps/real-apps-docker/bugsink", "docker"),
        ("apps/real-apps-native/bugsink", "native"),
        ("apps/real-apps-nix/bugsink", "nix"),
        ("apps/real-apps-nix-gen/bugsink", "nix-template"),  # before "real-apps-nix"
        ("apps/test-apps-nix/flask-hello", "nix"),
        ("apps/test-apps-procfile/000-static", "procfile"),
        ("apps/bad/real-apps-native-bad/monica", "native"),  # bad recipe keeps flavor
        ("apps/internal-apps/aipress24", "internal"),
        ("apps/sandbox/docker-flask-example", "sandbox"),
        ("demos/demo14", "demo"),
        ("docs/src/tutorials/python/flask", "tutorial"),
        ("focalboard", "other"),  # bare id (not path-qualified)
        (None, "other"),
    ],
)
def test_variant_of(name, expected):
    assert variant_of(name) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("apps/real-apps-docker/bugsink", "bugsink"),
        ("demos/demo14", "demo14"),
        ("focalboard", "focalboard"),
        (None, "—"),
        # A generic container leaf is skipped in favour of the parent, so two
        # demos' app subdirs don't both collapse to the indistinguishable "app".
        ("demos/demo15/app", "demo15"),
        ("demos/demo16/app", "demo16"),
        ("apps/real-apps-native/monica/src", "monica"),
        ("app", "app"),  # bare generic leaf: nothing to fall back to
    ],
)
def test_short_app(name, expected):
    assert short_app(name) == expected
