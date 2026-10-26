# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The demos and fixture apps carry the lockfiles their toolchains require.

The Node and Ruby toolchains refuse to build without a lockfile. A Docker
build installs inside its image and a Nix build through its template, so
neither is held to it here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

LOCKFILES = {
    "package.json": ("package-lock.json", "npm-shrinkwrap.json"),
    "Gemfile": ("Gemfile.lock",),
}


def _native_app_dirs(repo_root: Path) -> list[Path]:
    dirs = [*repo_root.glob("demos/demo*/app"), *repo_root.glob("apps/*/*")]
    return [
        d
        for d in dirs
        if not (d / "Dockerfile").exists()
        and not d.parent.name.startswith("test-apps-nix")
    ]


def test_native_demos_and_fixtures_have_lockfiles(repo_root):
    dirs = _native_app_dirs(repo_root)
    assert dirs, "no app directories found"
    missing = [
        str(d / manifest)
        for d in dirs
        for manifest, locks in LOCKFILES.items()
        if (d / manifest).exists() and not any((d / lock).exists() for lock in locks)
    ]
    assert missing == [], f"no lockfile beside: {missing}"
