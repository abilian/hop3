# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Only a path the gate reads unambiguously can be public (ADR 062, ADR 050 §2).

A public path skips the sign-in, so a path the app could route differently
from the gate must not match one. Every such path counts as not public.
"""

from __future__ import annotations

import pytest

from hop3.server.security.access_gate import canonical_path, is_public

PUBLIC = ["/hook", "/api/public/.*"]


@pytest.mark.parametrize(
    "uri",
    [
        "/hook",
        "/hook?token=1",
        "/%68ook",  # one layer of encoding, decoded once
        "/api/public/status",
        "/api/public/a%20b",
    ],
)
def test_a_public_path_is_public(uri):
    assert is_public(uri, PUBLIC)


@pytest.mark.parametrize(
    "uri",
    [
        "/hook/",  # full match: a trailing slash is another path
        "/hooks",
        "/admin",
        "/admin?next=/hook",  # the query string is not the path
    ],
)
def test_other_paths_are_not(uri):
    assert not is_public(uri, PUBLIC)


@pytest.mark.parametrize(
    "uri",
    [
        "/admin/../hook",
        "/admin/%2e%2e/hook",
        "/./hook",
        "//hook",
        "/admin%2F..%2Fhook",
        "/admin%2fhook",
        "/%2568ook",  # double-encoded
        "/hook%00",
        "/hook\\",
        "hook",
    ],
)
def test_an_ambiguous_path_is_never_public(uri):
    assert canonical_path(uri) is None
    assert not is_public(uri, [*PUBLIC, ".*"])
