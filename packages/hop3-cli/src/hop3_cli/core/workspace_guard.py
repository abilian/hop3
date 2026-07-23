# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Fail-loud guard against deploying a uv-workspace member in isolation.

When an app directory is a member of a uv workspace (a parent
``pyproject.toml`` has ``[tool.uv.workspace]`` whose ``members`` glob the
directory) and it depends on *another* member of that workspace, deploying the
directory by itself does not ship the sibling's source. The server then
installs the sibling from PyPI — a published release, not the local code — and
silently runs stale code. (This is exactly how the Test Lab kept running a
pre-fix ``hop3-testing`` engine for days: ``hop3 deploy packages/hop3-testlab``
pulled ``hop3-testing`` from PyPI.)

Per the "no silent fallback" rule, we refuse such a deploy up front with an
actionable message, rather than let it quietly install the wrong code. The
escape hatch is explicit: pin the sibling to a released version (``==``) to opt
into the PyPI release on purpose, or pass ``--force``.

Detection is pure and best-effort: any unreadable/odd pyproject yields "no
problem" so the guard never blocks a deploy on its own parsing quirks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomllib

#: A PEP 508 requirement starts with the distribution name; capture it before
#: any extras ``[...]``, version specifier, or ``;`` marker.
_REQ_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")

#: An exact pin (``==`` / ``===``) signals deliberate intent to use a specific
#: released version; anything looser (bare name, ``>=``, ``~=``) resolves to
#: "newest matching on PyPI" — the staleness trap the guard exists to catch.
_EXACT_PIN_RE = re.compile(r"===?")


@dataclass(frozen=True)
class WorkspaceDepIssue:
    """
    Result of the workspace-dependency check.

    Attributes:
        is_problem: True iff the guard should fire.
        app_dir: The deploy source directory that was inspected.
        siblings: Names of the in-workspace packages it depends on (unpinned).
        workspace_root: The directory holding the workspace ``pyproject.toml``.
        message: A formatted multi-line refusal ready to print to stderr.
            Empty when ``is_problem`` is False.
    """

    is_problem: bool
    app_dir: Path | None = None
    siblings: tuple[str, ...] = ()
    workspace_root: Path | None = None
    message: str = ""


def check_workspace_dependency(
    source_dir: Path, *, home: Path | None = None
) -> WorkspaceDepIssue:
    """
    Detect an isolated deploy of a uv-workspace member with an internal dep.

    Args:
        source_dir: The directory ``hop3 deploy`` would package.
        home: Upper bound for the upward search (defaults to ``Path.home()``).

    Returns:
        ``WorkspaceDepIssue(is_problem=True, ...)`` only when ``source_dir`` is
        a strict member of an enclosing uv workspace AND depends on another
        member of that workspace without an exact-version pin.
    """
    home = (home or Path.home()).resolve()
    source_dir = source_dir.resolve()

    src_data = _read_toml(source_dir / "pyproject.toml")
    if not src_data:
        # No pyproject (or unreadable) -> nothing to reason about.
        return WorkspaceDepIssue(is_problem=False)

    found = _find_enclosing_workspace(source_dir, home)
    if found is None:
        return WorkspaceDepIssue(is_problem=False)
    workspace_root, member_dirs = found

    member_names = _member_package_names(member_dirs)
    own_name = _normalize(_project_name(src_data))

    offenders = []
    for spec in _dependencies(src_data):
        name = _normalize(_requirement_name(spec))
        if not name or name == own_name:
            continue
        if name in member_names and not _is_exactly_pinned(spec):
            offenders.append(name)

    if not offenders:
        return WorkspaceDepIssue(is_problem=False)

    siblings = tuple(dict.fromkeys(offenders))  # de-dupe, keep order
    return WorkspaceDepIssue(
        is_problem=True,
        app_dir=source_dir,
        siblings=siblings,
        workspace_root=workspace_root,
        message=_format_message(source_dir, siblings, workspace_root),
    )


def _find_enclosing_workspace(
    source_dir: Path, home: Path
) -> tuple[Path, set[Path]] | None:
    """
    Find the nearest ancestor that declares ``source_dir`` a workspace member.

    Walks strictly upward from ``source_dir`` (so a directory that is itself a
    workspace root — i.e. you're deploying the whole workspace — does not
    match). Capped at ``home``.
    """
    current = source_dir.parent
    while True:
        data = _read_toml(current / "pyproject.toml")
        members = _workspace_members(data)
        if members is not None:
            member_dirs = _resolve_members(current, members)
            if source_dir in member_dirs:
                return current, member_dirs
        if current in {home, current.parent}:
            return None
        current = current.parent


def _resolve_members(root: Path, patterns: list[str]) -> set[Path]:
    """Expand workspace ``members`` globs to the member directories on disk."""
    dirs: set[Path] = set()
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_dir() and (path / "pyproject.toml").is_file():
                dirs.add(path.resolve())
    return dirs


def _member_package_names(member_dirs: set[Path]) -> set[str]:
    """The normalized distribution names declared by each member package."""
    names = set()
    for directory in member_dirs:
        name = _normalize(_project_name(_read_toml(directory / "pyproject.toml")))
        if name:
            names.add(name)
    return names


def _format_message(
    source_dir: Path, siblings: tuple[str, ...], workspace_root: Path
) -> str:
    app = _project_name(_read_toml(source_dir / "pyproject.toml")) or source_dir.name
    rel = _display_path(source_dir)
    sib_list = ", ".join(f"{s!r}" for s in siblings)
    plural = "s" if len(siblings) > 1 else ""
    return (
        f"Refusing to deploy {app!r} from {rel}: it depends on {sib_list}, "
        f"package{plural} in the enclosing uv workspace "
        f"({_display_path(workspace_root)}/pyproject.toml).\n"
        f"\n"
        f"Deploying this directory alone does not ship the sibling source, so "
        f"the server installs {'them' if plural else 'it'} from PyPI — a "
        f"published release, not your local code (silent staleness).\n"
        f"\n"
        f"  - Deploy from the workspace so the source ships and installs from "
        f"source, or\n"
        f"  - pin {('each of ' + sib_list) if plural else sib_list} to "
        f"'==<version>' in pyproject.toml to use the PyPI release on purpose.\n"
        f"\n"
        f"(override with --force to deploy the isolated directory anyway.)"
    )


def _display_path(path: Path) -> str:
    """Show ``path`` relative to CWD when possible, else absolute."""
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def _read_toml(path: Path) -> dict[str, Any]:
    """Parse a pyproject.toml; ``{}`` on any read/parse failure (best-effort)."""
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _workspace_members(data: dict[str, Any]) -> list[str] | None:
    members = data.get("tool", {}).get("uv", {}).get("workspace", {}).get("members")
    return members if isinstance(members, list) else None


def _project_name(data: dict[str, Any]) -> str:
    name = data.get("project", {}).get("name", "")
    return name if isinstance(name, str) else ""


def _dependencies(data: dict[str, Any]) -> list[str]:
    deps = data.get("project", {}).get("dependencies", [])
    return [d for d in deps if isinstance(d, str)] if isinstance(deps, list) else []


def _requirement_name(spec: str) -> str:
    match = _REQ_NAME_RE.match(spec)
    return match.group(1) if match else ""


def _is_exactly_pinned(spec: str) -> bool:
    return bool(_EXACT_PIN_RE.search(spec))


def _normalize(name: str) -> str:
    """PEP 503 normalization so ``Hop3_Testing`` == ``hop3-testing``."""
    return re.sub(r"[-_.]+", "-", name).lower()
