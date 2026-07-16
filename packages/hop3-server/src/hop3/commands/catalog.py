# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Catalog CLI/RPC commands (ADR 049)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from hop3.lib.args import pop_app_flag
from hop3.lib.registry import register
from hop3.server.catalog.install import CatalogInstallError, stage_catalog_app
from hop3.server.catalog.refresh import refresh_catalog
from hop3.server.catalog.service import CatalogService
from hop3.server.catalog.sync import CatalogSyncError
from hop3.server.catalog.verify import CatalogVerificationError

from ._base import Command
from ._deploy import deploy_app_streaming
from ._response import error, table, text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@register
class CatalogCmd(Command):
    """Browse and install apps from the Hop3 app catalog.

    Examples:
        hop3 catalog list                        # list available apps
        hop3 catalog install <id>                # install and deploy an app
        hop3 catalog refresh                     # fetch the latest signed catalog
    """

    name: ClassVar[tuple[str, ...]] = ("catalog",)


@register
class CatalogRefreshCmd(Command):
    """Fetch and install the latest signed app catalog.

    Downloads the catalog tarball from the configured source, verifies its
    minisign signature against the key pinned in this build, checks it is not a
    rollback, and publishes it atomically. On any failure the previously
    published catalog is left untouched.

    Usage: hop3 catalog refresh
    """

    name: ClassVar[tuple[str, ...]] = ("catalog", "refresh")

    def call(self, *args, **kwargs) -> list:
        try:
            serial = refresh_catalog()
        except (CatalogSyncError, CatalogVerificationError) as e:
            return [error(f"Catalog refresh failed: {e}")]
        return [text(f"Catalog refreshed to serial {serial}.")]


@register
class CatalogListCmd(Command):
    """List the applications available in the published catalog.

    Reads the catalog currently published on this server (see
    ``hop3 catalog refresh``). Each row is a blueprint you can install with
    ``hop3 catalog install <id> --app <name>``.

    Usage: hop3 catalog list
    """

    name: ClassVar[tuple[str, ...]] = ("catalog", "list")

    def call(self, *args, **kwargs) -> list:
        service = CatalogService.get_instance()
        if not service.is_available():
            # Fail loud: an empty table would read as "catalog has no apps".
            return [
                error(
                    "No catalog is published on this server yet. "
                    "Fetch one with: hop3 catalog refresh"
                )
            ]

        apps = service.list_apps()
        if not apps:
            return [text("The published catalog contains no apps.")]

        rows = [
            [app.id, app.title, app.category or "-", app.license or "-"]
            for app in sorted(apps, key=lambda a: a.id)
        ]
        return [table(headers=["ID", "Title", "Category", "License"], rows=rows)]


_USAGE = (
    "Usage: hop3 catalog install <app-id> "
    "[--app NAME] [--domain HOST] [--env KEY=VALUE]"
)


def _parse_install_rest(
    rest: list[str],
) -> tuple[str | None, list[str], list[str], str | None]:
    """From the tokens after ``--app`` is removed, pull the blueprint id (a lone
    positional), any ``--env`` / ``-e`` ``KEY=VALUE`` pairs, and an optional
    ``--domain`` / ``-d`` ``<host>``.

    Returns ``(app_id, env_lines, extras, domain)``; ``extras`` collects anything
    unexpected so the caller can reject it loudly rather than ignore it.
    """
    app_id: str | None = None
    env_lines: list[str] = []
    extras: list[str] = []
    domain: str | None = None
    i = 0
    while i < len(rest):
        tok = rest[i]
        if tok in {"--env", "-e"} and i + 1 < len(rest):
            env_lines.append(rest[i + 1])
            i += 2
            continue
        if tok.startswith("--env="):
            env_lines.append(tok.partition("=")[2])
            i += 1
            continue
        if tok in {"--domain", "-d"} and i + 1 < len(rest):
            domain = rest[i + 1]
            i += 2
            continue
        if tok.startswith("--domain="):
            domain = tok.partition("=")[2]
            i += 1
            continue
        if tok.startswith("-"):
            extras.append(tok)
        elif app_id is None:
            app_id = tok
        else:
            extras.append(tok)
        i += 1
    return app_id, env_lines, extras, domain


@register
@dataclass(frozen=True)
class CatalogInstallCmd(Command):
    """Install an app from the published catalog and deploy it.

    Stages the blueprint's tested recipe as a new hop3 app, then builds and runs
    it (streaming the deploy logs live, like ``hop3 deploy``). The instance is
    named after the blueprint id by default; pass ``--app`` to choose a different
    name (e.g. to run two instances). It is reachable straight away: unless
    ``--domain`` is given the app gets ``<name>.<admin-domain>``. Remove it later
    with ``hop3 app destroy --app <name>``.

    Examples:
        hop3 catalog install bookstack
        hop3 catalog install nextcloud --app mycloud
        hop3 catalog install nextcloud --app mycloud --domain cloud.example.com
        hop3 catalog install gitea --app git --env RUN_MODE=prod
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("catalog", "install")

    def call(self, *args, **kwargs) -> list:
        app_name, rest = pop_app_flag(args)
        app_id, env_lines, extras, domain = _parse_install_rest(rest)

        if extras:
            joined = " ".join(extras)
            return [error(f"Unexpected argument(s): {joined}\n{_USAGE}")]
        if not app_id:
            return [error(_USAGE)]
        # --app is optional: default the instance name to the blueprint id, so
        # `hop3 catalog install bookstack` installs an app named "bookstack".
        app_name = app_name or app_id

        env_vars = "\n".join(env_lines)
        try:
            app = stage_catalog_app(
                app_id, app_name, env_vars, self.db_session, domain=domain
            )
        except CatalogInstallError as e:
            return [error("Cannot install: " + "; ".join(e.errors))]

        # Build + run in the background, streaming logs to the CLI (identical to
        # `hop3 deploy`). The app row is committed by stage_catalog_app, so the
        # deploy thread's own session can see it.
        return [deploy_app_streaming(app_name, app.id)]
