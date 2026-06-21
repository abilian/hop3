# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Git app sources: fetch a repo at a chosen ref into a local workspace.

v2 spec §A: a run composes independently-versioned inputs. The apps under test
come from a named git **source** at a chosen **ref** — not the Test Lab's own
checkout. This module clones a source once into a per-source cache and checks out
a given ref into an isolated worktree, so the worker can build a catalog and
deploy apps from ``source@ref`` while the platform installs a *different* ref.

Slice-1 scope: one source, public repo, branch/tag/sha. Multiple sources at once
and private-repo deploy keys are deferred (see ``tasks/todo.md``).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

# Source clones and per-ref worktrees, sibling to the result store under ~/.hop3.
SOURCES_ROOT = Path.home() / ".hop3" / "testlab" / "sources"
WORKSPACES_ROOT = Path.home() / ".hop3" / "testlab" / "workspaces"


def _git(*args: str, cwd: Path | None = None) -> str:
    """Run git, return stripped stdout; raise loud (with stderr) on failure."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        cmd = "git " + " ".join(args)
        msg = f"Source fetch can't run `{cmd}`: {result.stderr.strip()}"
        raise RuntimeError(msg)
    return result.stdout.strip()


def _sanitize(value: str) -> str:
    """A filesystem-safe leaf for a name/ref (slashes & specials -> '_')."""
    return "".join(c if c.isalnum() or c in "-._" else "_" for c in value)


@dataclass(frozen=True, slots=True)
class Source:
    """A named git repository the Test Lab fetches apps from."""

    name: str
    url: str

    @property
    def cache(self) -> Path:
        """The persistent clone for this source (objects shared across refs)."""
        return SOURCES_ROOT / _sanitize(self.name)

    def fetch(self, ref: str) -> Path:
        """Check out ``ref`` into an isolated worktree; return its path.

        Clones once into the per-source cache, fetches, resolves ``ref`` (branch,
        tag, or sha), and lays down a *clean* detached worktree for it. The
        worktree is recreated each call so the tree is exactly ``ref`` with no
        leftovers from a previous checkout — runs must be reproducible.
        """
        if not (self.cache / ".git").exists():
            self.cache.parent.mkdir(parents=True, exist_ok=True)
            _git("clone", self.url, str(self.cache))
        _git("fetch", "--tags", "--force", "origin", cwd=self.cache)

        rev = self._resolve(ref)
        workspace = WORKSPACES_ROOT / _sanitize(self.name) / _sanitize(ref)
        # Recreate the worktree so it's a clean checkout of `rev`, no stale files.
        # ponytail: assumes ~/.hop3/testlab worktrees are ours; rm -rf that dir if
        # it ever gets corrupted out-of-band.
        _git("worktree", "prune", cwd=self.cache)
        if workspace.exists():
            _git("worktree", "remove", "--force", str(workspace), cwd=self.cache)
        workspace.parent.mkdir(parents=True, exist_ok=True)
        _git(
            "worktree",
            "add",
            "--detach",
            "--force",
            str(workspace),
            rev,
            cwd=self.cache,
        )
        return workspace

    def _resolve(self, ref: str) -> str:
        """Resolve a branch/tag/sha to a commit sha (raise loud if unknown)."""
        for candidate in (f"origin/{ref}", ref):
            try:
                return _git(
                    "rev-parse",
                    "--verify",
                    "--quiet",
                    f"{candidate}^{{commit}}",
                    cwd=self.cache,
                )
            except RuntimeError:
                continue
        msg = (
            f"Source {self.name!r} can't resolve ref {ref!r}: "
            "not a branch, tag, or commit"
        )
        raise RuntimeError(msg)
