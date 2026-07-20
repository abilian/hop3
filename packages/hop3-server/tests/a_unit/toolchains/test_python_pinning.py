# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Dependency-pinning checks for the Python toolchain.

An unpinned requirement resolves to whatever satisfies it on the day of the
build, so the same commit can deploy different code twice. The toolchain
refuses to build in that case rather than producing an unreproducible result.
"""

from __future__ import annotations

from hop3.toolchains.python import (
    requirements_are_hashed,
    unpinned_requirements,
)

PINNED = """\
# comment
flask==3.0.0
gunicorn==21.2.0
"""

HASHED = """\
flask==3.0.0 \\
    --hash=sha256:aaaa
gunicorn==21.2.0 \\
    --hash=sha256:bbbb
"""

UNPINNED = """\
flask
gunicorn>=21.0
requests==2.31.0
"""


def test_pinned_requirements_pass():
    assert unpinned_requirements(PINNED) == []


def test_unpinned_requirements_are_reported():
    unpinned = unpinned_requirements(UNPINNED)
    assert "flask" in unpinned
    assert "gunicorn>=21.0" in unpinned
    # a properly pinned entry in the same file is not flagged
    assert "requests==2.31.0" not in unpinned


def test_options_and_includes_are_not_requirements():
    text = "-r base.txt\n--index-url https://example.invalid\n-e .\nflask==1.0\n"
    assert unpinned_requirements(text) == []


def test_hashed_requirements_detected():
    """Continuations are joined, so the hash belongs to its requirement."""
    assert requirements_are_hashed(HASHED)


def test_version_pinning_alone_is_not_hashed():
    assert not requirements_are_hashed(PINNED)


def test_empty_file_is_not_considered_hashed():
    assert not requirements_are_hashed("# nothing here\n")
