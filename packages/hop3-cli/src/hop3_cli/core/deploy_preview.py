# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Build and render the deploy preview (ADR 042 §Deploy preview).

``hop3 deploy`` becomes "destructive-ish": before sending the deploy
RPC, the CLI prints a plan of what's about to happen and prompts the
operator for confirmation. The plan is what the new resolver knows
atomically — source path + git state, context, app, domains,
addons, env-var changes.

Pure rendering layer: this module computes and formats the plan; the
caller (main.py) decides whether to print, prompt, dry-run-exit, or
skip-and-proceed based on operator flags.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from hop3_cli.core.hop3_toml import first_hop3_toml, read_hop3_toml

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True)
class GitState:
    """Snapshot of the source's git state, or empty if not in a repo."""

    commit: str = ""
    branch: str = ""
    dirty: bool = False
    is_repo: bool = False

    @property
    def descriptor(self) -> str:
        """Human-readable string for the preview's Source line."""
        if not self.is_repo:
            return "(not a git repo)"
        parts = []
        if self.branch:
            parts.append(self.branch)
        if self.commit:
            parts.append(f"@ {self.commit[:7]}")
        if self.dirty:
            parts.append("(dirty)")
        return " ".join(parts) if parts else "(unknown state)"


@dataclass(frozen=True)
class DeployPlan:
    """
    Materialised view of what ``hop3 deploy`` is about to do.

    All fields are best-effort: missing hop3.toml, no git repo, etc.
    don't fail — the plan still renders with empty / "(none)" markers
    so the operator can see what's known and what isn't.
    """

    source_path: Path
    git: GitState
    context: str | None
    app: str
    domains: tuple[str, ...]
    addons: tuple[str, ...]
    env_keys: tuple[str, ...] = field(default_factory=tuple)
    # The address the deploy will actually connect to (ADR 042: the context IS
    # the server). Resolved by the caller from the active/ambient server, so the
    # preview names the real target, not just the context label.
    server: str | None = None
    # When no context was explicitly resolved, the default context that selected
    # ``server`` (``[cli].default_context``). Display-only: the upload still
    # flattens on ``context`` so preview == deploy. None when the server came
    # from elsewhere (env var, default_server, sole known server).
    default_context: str | None = None
    # Path of an ancestor hop3.toml that EXISTS but isn't being packaged
    # (the deploy archive root is ``source_path``, so the ancestor's
    # domains/addons/env won't make it to the server). Surfaces as a
    # warning so the operator notices they're deploying from a subdir.
    ancestor_hop3_toml: Path | None = None


def build_plan(
    *,
    source_path: Path,
    context: str | None,
    app: str,
    server: str | None = None,
    default_context: str | None = None,
    home: Path | None = None,
    git_runner: Callable[[list[str], Path], str | None] | None = None,
) -> DeployPlan:
    """
    Build the deploy plan from the resolved inputs.

    Reads ``source_path / hop3.toml`` ONLY — not an ancestor's. The
    deploy archive (``pack_repository`` in commands/arguments.py) only
    packages files inside ``source_path``; an ancestor's hop3.toml is
    never sent to the server, so showing its domains/addons in the
    preview would lie about the deploy.

    As a separate diagnostic, ``build_plan`` walks upward (capped at
    ``home``) to find an ancestor hop3.toml; if one exists, the path is
    captured on ``DeployPlan.ancestor_hop3_toml`` and ``render_plan``
    surfaces a warning so the operator notices they may be deploying
    from a project subdirectory.

    Reads git state via ``git_runner`` (a callable accepting
    ``(argv: list[str], cwd: Path)`` and returning stdout or None on
    failure; defaults to the subprocess wrapper). Pure with respect to
    its inputs.

    Args:
        source_path: The directory the deploy is being driven from.
            ``source_path / hop3.toml`` is the only TOML the deploy will
            ever see.
        context: Resolved context name (or None when unresolved). The context
            IS the server (ADR 042). Used to flatten the hop3.toml, so the
            preview matches the upload exactly.
        app: Resolved app name.
        server: The address the deploy will connect to (display-only).
        default_context: The default context that selected ``server`` when no
            context was explicitly resolved (display-only).
        home: Upper bound for the ancestor-walk diagnostic (defaults to
            ``Path.home()``).
        git_runner: Test seam.
    """
    git = _collect_git_state(source_path, git_runner)

    own_path = source_path / "hop3.toml"
    raw = read_hop3_toml(own_path) if own_path.is_file() else {}
    # Flatten the selected context in (merge env, replace domains, strip
    # [contexts.*]) so the preview reflects EXACTLY the effective config the
    # deploy uploads — preview == deploy (ADR 042 r2 §E1). With the context
    # already merged, the display helpers run with no separate context block.
    data = flatten_for_context(raw, context)

    domains = _all_domains(data)
    addons = _addon_names(data)
    env_keys = _resolved_env_keys(data)

    # Ancestor-hop3-toml diagnostic. Only fires when source_path itself
    # has no hop3.toml but an ancestor does — the "operator is deploying
    # from a subdir" footgun. If source_path HAS its own hop3.toml,
    # there's nothing to warn about (the deploy will package it).
    ancestor: Path | None = None
    if not own_path.is_file():
        found_path, _ = first_hop3_toml(source_path, home or Path.home())
        if found_path is not None and found_path != own_path:
            ancestor = found_path

    return DeployPlan(
        source_path=source_path,
        git=git,
        context=context,
        app=app,
        domains=tuple(domains),
        addons=tuple(addons),
        env_keys=tuple(env_keys),
        server=server,
        default_context=default_context,
        ancestor_hop3_toml=ancestor,
    )


def render_plan(plan: DeployPlan) -> str:
    """
    Format the plan as a multi-line string ready to print to stdout.

    Layout matches the ADR's §Deploy preview example. Empty fields
    surface as ``(none)`` rather than being omitted, so the operator
    always sees a consistent set of rows.
    """
    lines = ["About to deploy:"]
    lines.append(f"  Source:   {plan.source_path} ({plan.git.descriptor})")
    if plan.context:
        lines.append(f"  Context:  {plan.context}")
    elif plan.default_context:
        lines.append(f"  Context:  {plan.default_context} (default)")
    else:
        lines.append("  Context:  (none)")
    lines.append(f"  Server:   {plan.server or '(none)'}")
    lines.append(f"  App:      {plan.app}")
    lines.append(f"  Domains:  {', '.join(plan.domains) if plan.domains else '(none)'}")
    lines.append(f"  Addons:   {', '.join(plan.addons) if plan.addons else '(none)'}")
    if plan.env_keys:
        env_summary = ", ".join(sorted(plan.env_keys))
        lines.append(f"  Env vars: {env_summary}")
    else:
        lines.append("  Env vars: (none)")
    if plan.git.dirty:
        lines.append("")
        lines.append("  warning: source tree has uncommitted changes")
    if plan.ancestor_hop3_toml is not None:
        lines.append("")
        lines.append(
            f"  warning: {plan.source_path} has no hop3.toml; ancestor at "
            f"{plan.ancestor_hop3_toml} will NOT be included in the deploy"
        )
    return "\n".join(lines)


# ---- DNS host-check (does the domain point at the deploy target?) --------


def domain_target_warnings(
    domains: tuple[str, ...] | list[str],
    api_url: str | None,
    *,
    resolver: Callable[[str], set[str]] | None = None,
) -> list[str]:
    """
    Warn when an app domain doesn't resolve to the deploy-target server.

    The #1 invisible-502: the app is deployed and healthy on server A, but the
    domain's DNS still points at server B (a CDN, an old box, a typo'd
    context), so every browser request lands somewhere else and 502s — while
    ``hop3 app logs`` shows a perfectly happy app, because requests never reach
    it. We catch it client-side at deploy time, where the target host (the
    api_url we're about to connect to) and the app's domains are both known.

    Best-effort and non-blocking: if the target host or a domain can't be
    resolved, that domain is skipped (we never guess). A CDN/proxy in front of
    the domain is a legitimate mismatch, so the message says so rather than
    crying wolf.

    Args:
        domains: the app's hostnames (see ``_all_domains``).
        api_url: the server URL we're deploying through (ssh://… or http://…).
        resolver: test seam; defaults to a best-effort DNS lookup.
    """
    resolve = resolver or resolve_host_ips
    target_host = _host_from_url(api_url)
    if not target_host:
        return []
    target_ips = resolve(target_host)
    if not target_ips:
        return []  # can't determine the target's IP — don't guess

    warnings: list[str] = []
    for domain in domains:
        if domain == target_host:
            continue
        domain_ips = resolve(domain)
        if not domain_ips:
            continue  # unresolvable (not yet registered, internal, etc.) — skip
        if domain_ips.isdisjoint(target_ips):
            warnings.append(
                f"domain {domain} resolves to {', '.join(sorted(domain_ips))}, "
                f"but you're deploying to {target_host} "
                f"({', '.join(sorted(target_ips))}). Requests to {domain} will "
                f"NOT reach this deploy — fix the domain's DNS, or deploy to the "
                f"server it points to. (If {domain} sits behind a CDN/proxy, "
                f"this is expected.)"
            )
    return warnings


def resolve_host_ips(host: str, *, timeout: float = 2.0) -> set[str]:
    """
    Best-effort resolve ``host`` to its set of IPv4/IPv6 addresses.

    Returns an empty set on any failure (unknown host, timeout, etc.) — the
    caller treats "couldn't resolve" as "don't warn", never as an error.
    """
    if not host:
        return set()
    old = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return set()
    finally:
        socket.setdefaulttimeout(old)
    # info[4][0] is the address string; getaddrinfo's sockaddr is typed as a
    # union (IPv4 vs IPv6), so coerce to str to satisfy the declared return.
    return {str(info[4][0]) for info in infos}


def _host_from_url(api_url: str | None) -> str:
    """Extract the bare host from an api_url (ssh://user@host[:port], http://…)."""
    if not api_url:
        return ""
    parsed = urlparse(api_url)
    if parsed.hostname:
        return parsed.hostname
    # api_url may be a bare host:port or host without a scheme.
    return api_url.split("@")[-1].split(":")[0].strip("/")


# ---- internals ----------------------------------------------------------


def _context_block(data: dict[str, Any], context: str) -> dict[str, Any] | None:
    """Return the ``[contexts.<context>]`` table or None."""
    contexts = data.get("contexts", {})
    if isinstance(contexts, dict):
        block = contexts.get(context)
        if isinstance(block, dict):
            return block
    return None


def flatten_for_context(
    data: dict[str, Any], context_name: str | None
) -> dict[str, Any]:
    """
    Produce the EFFECTIVE hop3.toml for a deploy (ADR 042 r2, §E1).

    Merges the selected context into the top level and strips every
    ``[contexts.*]`` block (the latter is never uploaded — decision §E1):

    - ``domains``: the context's domains (the ``[domains].list`` shape, or a
      bare list, both tolerated) fully REPLACE top-level ``[domains]`` when set.
    - ``env``: the context's ``env`` keys MERGE over top-level ``[env]``.

    Both the deploy preview and the actual upload call this, so the preview shows
    exactly what is deployed. Returns a new dict; ``data`` is not mutated.
    """
    result = dict(data)
    block = _context_block(data, context_name) if context_name else None
    if block is not None:
        if "domains" in block:
            raw = block.get("domains")
            hosts = raw.get("list") if isinstance(raw, dict) else raw
            result["domains"] = {"list": [h for h in hosts or [] if isinstance(h, str)]}
        ctx_env = block.get("env")
        if isinstance(ctx_env, dict):
            merged = dict(data.get("env") or {})
            merged.update(ctx_env)
            result["env"] = merged
    result.pop("contexts", None)
    return result


def _all_domains(data: dict[str, Any]) -> list[str]:
    """
    Every hostname this app will be served at (deduped, order-preserving).

    Union of ``[domains].list`` AND the legacy ``HOST_NAME`` env var (the proxy
    serves whatever HOST_NAME names). ``data`` is already context-flattened by
    ``flatten_for_context`` before this runs, so there is no separate context
    block to consider. Without the HOST_NAME source, an app that sets only
    ``[env].HOST_NAME`` (like many real apps) shows "Domains: (none)" in the
    preview and is skipped by the DNS host-check — which is exactly how a
    deploy-to-the-wrong-server 502 slips through unnoticed.
    """
    out: list[str] = []
    seen: set[str] = set()
    for d in (*_resolved_domains(data), *_host_name_domains(data)):
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def _resolved_domains(data: dict[str, Any]) -> list[str]:
    """The hostnames from the (already context-flattened) ``[domains].list``."""
    top = data.get("domains", {})
    if isinstance(top, dict):
        return [d for d in top.get("list") or [] if isinstance(d, str)]
    return []


def _host_name_domains(data: dict[str, Any]) -> list[str]:
    """
    Domains derived from the merged ``HOST_NAME`` env var.

    HOST_NAME may name multiple hosts (whitespace/comma-separated); the
    catch-all ``_`` and blanks are excluded. ``data`` is already
    context-flattened, so the merged HOST_NAME is just ``[env].HOST_NAME``.
    """
    host_name = ""
    base_env = data.get("env", {})
    if isinstance(base_env, dict) and isinstance(base_env.get("HOST_NAME"), str):
        host_name = base_env["HOST_NAME"]
    return [h for h in host_name.replace(",", " ").split() if h and h != "_"]


def _addon_names(data: dict[str, Any]) -> list[str]:
    """Extract addon type names from ``[[addons]]`` (or legacy ``[[provider]]``)."""
    addons = data.get("addons") or data.get("provider")
    if not isinstance(addons, list):
        return []
    out: list[str] = []
    for entry in addons:
        if not isinstance(entry, dict):
            continue
        name = entry.get("type") or entry.get("name")
        if isinstance(name, str) and name.strip():
            out.append(name.strip())
    return out


def _resolved_env_keys(data: dict[str, Any]) -> list[str]:
    """
    Names (not values) of env vars in the (context-flattened) ``[env]``.

    ``_policy`` / nested sub-tables are filtered out. ``data`` is already
    context-flattened, so this is just the merged top-level ``[env]``.
    """
    keys: set[str] = set()
    base = data.get("env", {})
    if isinstance(base, dict):
        for k, v in base.items():
            if not k.startswith("_") and not isinstance(v, dict):
                keys.add(k)
    return sorted(keys)


def _default_git_runner(argv: list[str], cwd: Path) -> str | None:
    """
    Run a git command and return stdout. Returns None on any failure.

    Kept tiny and side-effect-free: we don't raise on missing git, on a
    non-git directory, or on a command failure — those all just mean
    "no git state to show here".
    """
    import subprocess  # ruff:ignore[import-outside-top-level]

    try:
        result = subprocess.run(
            argv,
            cwd=str(cwd),
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _collect_git_state(
    source_path: Path,
    runner: Callable[[list[str], Path], str | None] | None = None,
) -> GitState:
    """Best-effort: gather (commit, branch, dirty). Empty on any failure."""
    run = runner or _default_git_runner

    head = run(["git", "rev-parse", "HEAD"], source_path)
    if head is None:
        return GitState(is_repo=False)
    commit = head.strip()

    branch_out = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], source_path)
    branch = branch_out.strip() if branch_out else ""

    # `git status --porcelain` is empty iff there are no uncommitted changes.
    status_out = run(["git", "status", "--porcelain"], source_path)
    dirty = bool(status_out and status_out.strip())

    return GitState(commit=commit, branch=branch, dirty=dirty, is_repo=True)
