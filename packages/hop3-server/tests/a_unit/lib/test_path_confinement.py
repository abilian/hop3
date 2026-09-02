# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Path confinement must resolve symlinks on both sides.

The regression: ``deployers/volumes.py`` confined a volume target with a
lexical ``normpath(...).startswith(root + os.sep)``. An in-tree symlink
(``src/data -> /etc``) is lexically inside the tree while pointing out of it,
so a declared target of ``data/x`` passed the check and the deployer then
seeded from and ``rmtree``-d through it. ``core/backup.py`` had already been
fixed the same way; the two now share one implementation.
"""

from __future__ import annotations

import os

from hop3.lib.path import is_confined_to, is_under


def test_is_under_accepts_the_root_and_its_children():
    assert is_under("/srv/app", "/srv/app")
    assert is_under("/srv/app/src", "/srv/app")


def test_is_under_rejects_a_sibling_sharing_a_prefix():
    assert not is_under("/srv/app-other", "/srv/app")


def test_confinement_accepts_a_real_path_inside(tmp_path):
    (tmp_path / "src" / "data").mkdir(parents=True)
    assert is_confined_to(tmp_path / "src" / "data", tmp_path / "src")


def test_confinement_rejects_traversal_through_an_in_tree_symlink(tmp_path):
    # The exploit: `src/data` is lexically inside src/, but resolves outside.
    src = tmp_path / "src"
    src.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (src / "data").symlink_to(outside)

    assert not is_confined_to(src / "data" / "x", src)


def test_lexical_check_would_have_passed_the_exploit(tmp_path):
    # Pins *why* realpath is required: the old check accepts the escape.
    src = tmp_path / "src"
    src.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (src / "data").symlink_to(outside)

    lexical = os.path.normpath(src / "data" / "x")
    assert lexical.startswith(str(src) + os.sep)  # old check: passes
    assert not is_confined_to(src / "data" / "x", src)  # new check: rejects
