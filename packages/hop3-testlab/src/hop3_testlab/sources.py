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

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Source clones and per-ref worktrees, sibling to the result store under ~/.hop3.
SOURCES_ROOT = Path.home() / ".hop3" / "testlab" / "sources"
WORKSPACES_ROOT = Path.home() / ".hop3" / "testlab" / "workspaces"

_ALLOWED_URL_PREFIXES = ("https://", "http://", "git://", "ssh://", "file://")
_SCP_LIKE = re.compile(r"^[A-Za-z0-9_.+-]+@[A-Za-z0-9_.-]+:")


def is_allowed_source_url(url: str) -> bool:
    """True if ``url`` is a safe git source: an allowed scheme, an scp-like
    ``user@host:path``, or an absolute local path.

    Rejects a leading ``-`` (git option injection) and the ``ext::``/``fd::``
    transport helpers (which can run commands on the host). Validated at
    profile-create time so a malicious URL never reaches ``git clone``.
    """
    url = url.strip()
    if not url or url.startswith("-"):
        return False
    if "::" in url.split("/", 1)[0]:  # ext::, fd:: and friends
        return False
    if url.startswith("/") or url.startswith(_ALLOWED_URL_PREFIXES):
        return True
    return bool(_SCP_LIKE.match(url))


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
            # `--` ends options so a URL can't be parsed as a git flag.
            _git("clone", "--", self.url, str(self.cache))
        _git("fetch", "--tags", "--force", "origin", cwd=self.cache)

        rev = self._resolve(ref)
        workspace = WORKSPACES_ROOT / _sanitize(self.name) / _sanitize(ref)
        # Recreate the worktree so it's a clean checkout of `rev`, no stale files.
        _git("worktree", "prune", cwd=self.cache)
        if workspace.exists():
            try:
                _git("worktree", "remove", "--force", str(workspace), cwd=self.cache)
            except RuntimeError:
                # A partial/corrupted worktree can't be `git worktree remove`'d and
                # would wedge every future fetch of this source — force it gone and
                # re-prune so the source self-heals (was a manual rm -rf).
                shutil.rmtree(workspace, ignore_errors=True)
                _git("worktree", "prune", cwd=self.cache)
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
