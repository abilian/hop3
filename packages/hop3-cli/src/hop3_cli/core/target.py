# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Where a command goes: the one resolver (ADR 042).

``resolve_context`` chooses a context name by rule B; ``resolve_target``
turns it into a server, or refuses. Every command, message and ``--why``
reads its answer, so no two of them can disagree about the target.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hop3_cli.core import credential_store
from hop3_cli.core.hop3_toml import read_hop3_toml
from hop3_cli.core.resolution import ContextResolution, ContextSource
from hop3_cli.exceptions import TargetError

if TYPE_CHECKING:
    from pathlib import Path

    from hop3_cli.config import Config

#: Keys a ``[contexts.<name>]`` block of hop3.toml may no longer carry: where
#: the app is deployed belongs to the developer's own contexts.
_ADDRESS_KEYS = ("server", "bootstrap")


@dataclass(frozen=True)
class Target:
    """The server this invocation reaches, and why."""

    context: str
    server: str
    bootstrap: str | None
    source: ContextSource

    def describe(self) -> str:
        """The one line every server-reaching command prints (rule C)."""
        return f"→ {self.context} ({self.server}), {self.source.value}"


def resolve_target(resolution: ContextResolution, config: Config) -> Target:
    """
    The server for ``resolution``, or a ``TargetError`` saying how to choose one.

    A name resolves or aborts, whichever step of rule B supplied it. Inside a
    project, the project's ``[contexts.*]`` blocks must not name a server and,
    when there are any, must include the chosen context.
    """
    if resolution.kind is ContextSource.UNBOUND and resolution.project:
        raise TargetError(_unbound_message(resolution.project, config))
    name = resolution.context
    if not name:
        raise TargetError(_unresolved_message(config))

    server = config.get_context_server(name)
    if not server:
        msg = (
            f"context {name!r} ({resolution.kind.value}) is not defined.\n"
            f"  Known: {_known(config)}\n"
            f"  Define it: hop3 context add {name} --server <address>"
        )
        raise TargetError(msg)
    if resolution.kind in {ContextSource.FLAG, ContextSource.ENV}:
        _refuse_env_url_conflict(name, resolution.kind, server, config)
    if resolution.project is not None:
        check_project_blocks(resolution.project, name)
    return Target(
        context=name,
        server=server,
        bootstrap=config.get_context_bootstrap(name),
        source=resolution.kind,
    )


def _known(config: Config) -> str:
    return ", ".join(sorted(config.list_global_contexts())) or "(none)"


def _unbound_message(project: Path, config: Config) -> str:
    return (
        f"this checkout ({project.parent}) is not bound to a context.\n"
        f"  Bind it:              hop3 context use <name>   (known: {_known(config)})\n"
        f"  or for one command:   hop3 -c <name> ..."
    )


def _unresolved_message(config: Config) -> str:
    if config.list_global_contexts():
        return (
            "no context selected.\n"
            f"  Choose one:   hop3 context use <name>   (known: {_known(config)})\n"
            "  or for one command:   hop3 -c <name> ..."
        )
    return (
        "not connected to a server yet.\n"
        "  Sign in over SSH:   hop3 login <user>@<host>\n"
        "  or with a token:    hop3 login --token <token> --url https://<host>"
    )


def _refuse_env_url_conflict(
    name: str, kind: ContextSource, server: str, config: Config
) -> None:
    """
    A context named explicitly must not be overridden by ``HOP3_API_URL``.

    The environment's URL and an explicit name sit at the same rank; when they
    disagree, the CLI connects to neither rather than guess.
    """
    env_url = config.env_context_server()
    if not env_url:
        return
    if credential_store.canonicalize(env_url) == credential_store.canonicalize(server):
        return
    msg = (
        f"context {name!r} ({kind.value}) targets {server}, but HOP3_API_URL / "
        f"HOP3_DEV_MODE points at {env_url}.\n"
        "  Unset one of them."
    )
    raise TargetError(msg)


def check_project_blocks(project: Path, name: str) -> None:
    """Refuse a project whose blocks name a server, or name other contexts only."""
    blocks = _context_blocks(read_hop3_toml(project))
    for block_name, block in blocks.items():
        if not any(key in block for key in _ADDRESS_KEYS):
            continue
        command = (
            f"hop3 context add {block_name} --server {block.get('server', '<address>')}"
        )
        if "bootstrap" in block:
            command += f" --bootstrap {block['bootstrap']}"
        msg = (
            f"[contexts.{block_name}] in {project} names a server: hop3.toml no "
            "longer says where the app is deployed.\n"
            f"  Record it as your own context:   {command}\n"
            f"  then remove {' and '.join(k for k in _ADDRESS_KEYS if k in block)} "
            f"from [contexts.{block_name}]."
        )
        raise TargetError(msg)
    if blocks and name not in blocks:
        msg = (
            f"context {name!r} matches none of the [contexts.*] blocks in {project} "
            f"({', '.join(sorted(blocks))}).\n"
            f"  Use one of them, or add a [contexts.{name}] block for it."
        )
        raise TargetError(msg)


def _context_blocks(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    contexts = data.get("contexts")
    if not isinstance(contexts, dict):
        return {}
    return {k: v for k, v in contexts.items() if isinstance(v, dict)}
