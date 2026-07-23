# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Shared catalog-install staging (ADR 049).

``stage_catalog_app`` is the single source of truth for turning a catalog
blueprint into a locally-created hop3 App: validate the target name, copy the
*verified* recipe into the app's source tree, attach env vars, and persist.
Both the CLI (``hop3 catalog install``) and the dashboard install form call it,
so the two surfaces behave identically.

It STAGES only — it never deploys. The caller triggers the deploy afterwards
(see ``hop3.commands._deploy.deploy_app_streaming``), so that the deploy runs
through the exact same streaming path as ``hop3 deploy``.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import tomllib

from hop3.commands._helpers import check_hostname_conflict, parse_hostname_string
from hop3.config import config
from hop3.core.identifiers import InvalidIdentifierError, validate_hostname
from hop3.orm import App, AppRepository, EnvVar
from hop3.server.catalog.service import CatalogService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from hop3.server.catalog.models import CatalogApp

# Names the platform reserves for its own routes / conventions.
_RESERVED_NAMES = {"admin", "api", "app", "apps", "dashboard", "hop3", "static", "www"}
_APP_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")


class CatalogInstallError(Exception):
    """
    Staging refused, with one or more human-readable reasons.

    Raised loudly instead of the old silent-skip / bare-redirect behaviour, so
    both the CLI and the UI can surface exactly why an install cannot proceed.
    """

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def stage_catalog_app(
    app_id: str,
    app_name: str,
    env_vars: str,
    db_session: Session,
    domain: str | None = None,
) -> App:
    """
    Create a hop3 App from a catalog blueprint — staged and persisted.

    Normalizes and validates ``app_name``, resolves the blueprint ``app_id`` in
    the published catalog, copies its recipe into the new app's source tree,
    attaches any ``env_vars`` (a newline-delimited ``K=V`` string), assigns a
    public hostname (``domain`` or ``<app>.<ADMIN_DOMAIN>``) so the first deploy
    makes it reachable, and commits on ``db_session``. Returns the persisted App
    (``.id`` assigned), ready to deploy.

    Raises ``CatalogInstallError`` (never silent) when the catalog is
    unavailable, the blueprint is unknown, its recipe is missing on disk, the
    name is invalid, an app of that name already exists, or the hostname is
    invalid / already in use.
    """
    app_name = app_name.strip().lower()

    service = CatalogService.get_instance()
    if not service.is_available():
        raise CatalogInstallError([
            "No catalog is published on this server. Run: hop3 catalog refresh"
        ])

    catalog_app = service.get_app(app_id)
    if catalog_app is None:
        raise CatalogInstallError([f"Unknown catalog app '{app_id}'"])

    # Fail loud rather than staging an empty app: the recipe dir must exist.
    # (The old _copy_catalog_source silently returned when it did not.)
    source_path = catalog_app.source_path
    if not source_path or not Path(source_path).is_dir():
        raise CatalogInstallError([
            f"Catalog app '{app_id}' has no recipe on disk to install"
        ])

    errors = _validate_app_name(app_name)
    if not errors and _check_app_exists(app_name, db_session):
        errors.append(f"An app named '{app_name}' already exists")
    if errors:
        raise CatalogInstallError(errors)

    app = App(name=app_name)
    app.create(setup_git=True)
    _copy_catalog_source(catalog_app, app)
    _parse_and_add_env_vars(app, env_vars)
    _assign_hostname(app, app_name, domain, db_session)

    # The recipe MUST have produced a hop3.toml at the src root, or the deploy
    # that follows is guaranteed to fail obscurely — surface it here instead.
    if not (Path(app.src_path) / "hop3.toml").is_file():
        raise CatalogInstallError([
            f"Recipe for '{app_id}' did not produce a hop3.toml; nothing to deploy"
        ])

    db_session.add(app)
    db_session.commit()
    return app


def _validate_app_name(app_name: str) -> list[str]:
    """Validate an app name; return a list of error strings (empty = valid)."""
    errors: list[str] = []
    if not app_name:
        errors.append("App name is required")
        return errors
    if len(app_name) < 2:
        errors.append("App name must be at least 2 characters")
    if len(app_name) > 50:
        errors.append("App name must be at most 50 characters")
    if not _APP_NAME_RE.match(app_name):
        errors.append(
            "App name must start with a letter and contain only lowercase "
            "letters, numbers, and hyphens"
        )
    if app_name in _RESERVED_NAMES:
        errors.append(f"'{app_name}' is a reserved name")
    return errors


def _check_app_exists(app_name: str, db_session: Session) -> bool:
    """
    True if an app with this name already exists (DB check).

    Uses the caller's install session (not a fresh one) so the check and the
    create-or-refuse decision are made against the same view — closing the
    check-then-create race a separate session would leave open.
    """
    return AppRepository(session=db_session).app_exists(app_name)


def _assign_hostname(
    app: App, app_name: str, domain: str | None, db_session: Session
) -> None:
    """
    Give the app a public hostname so the first deploy wires an nginx vhost.

    Precedence (most specific wins): a ``--env HOST_NAME`` the user passed, then
    an explicit ``domain``, then a recipe that pins its own ``[domains].list`` /
    ``[env].HOST_NAME``, then the auto-assigned ``<app>.<ADMIN_DOMAIN>`` default.
    Every resolved hostname — including one supplied via ``--env`` — is validated
    and conflict-checked, so no source can silently bind a bad or already-taken
    vhost. Without this a catalog app deploys with no HOST_NAME and the proxy
    step is skipped, leaving it reachable only on its loopback port (the reason a
    manual ``domain add`` + redeploy was needed). No-op (loopback-only, as
    before) when no hostname can be derived — no ``domain``, no recipe pin, and
    the server has no ``ADMIN_DOMAIN``.

    A recipe that pins ``[domains]`` with ``_policy = "override"`` will re-assert
    its own host at deploy time; that recipe-author choice is out of this staging
    step's scope.
    """
    # A user-provided --env HOST_NAME is already staged: it wins, but is still
    # validated and conflict-checked — never blindly trusted.
    existing = next((ev.value for ev in app.env_vars if ev.name == "HOST_NAME"), None)
    if existing is not None:
        _validate_and_check_hosts(parse_hostname_string(existing), app_name, db_session)
        return

    host = (domain or "").strip()
    if host == "_":
        # The user asked for a domain (promising reachability) but '_' is the
        # loopback catch-all, not a servable host — refuse rather than fail quiet.
        msg = (
            "'_' is the loopback catch-all, not a servable domain. "
            "Omit --domain to auto-assign, or pass a real hostname."
        )
        raise CatalogInstallError([msg])
    if not host:
        # No explicit domain: a recipe that pins its own hostname wins over the
        # auto-assigned default, so let its [domains] drive HOST_NAME at deploy.
        if _recipe_pins_hostname(app):
            return
        if config.ADMIN_DOMAIN:
            host = f"{app_name}.{config.ADMIN_DOMAIN}"
    if not host:
        return  # nothing to assign; app stays loopback-only (unchanged)

    _validate_and_check_hosts([host], app_name, db_session)
    app.env_vars.append(EnvVar(name="HOST_NAME", value=host))


def _validate_and_check_hosts(
    hosts: list[str], app_name: str, db_session: Session
) -> None:
    """
    Validate each host (RFC-1123) and refuse collisions — fail loud.

    Raises ``CatalogInstallError`` on an invalid host or one already used by
    another app (or the server's admin domain). The ``_`` catch-all is a valid
    sentinel but not a real host, so it is excluded from the conflict scan (many
    apps may be loopback-only at once).
    """
    real: list[str] = []
    for host in hosts:
        try:
            validate_hostname(host)
        except InvalidIdentifierError as exc:
            raise CatalogInstallError([f"Invalid hostname '{host}': {exc}"]) from exc
        if host != "_":
            real.append(host)

    conflict = check_hostname_conflict(db_session, app_name, real)
    if conflict is not None:
        other_app, host = conflict
        raise CatalogInstallError([
            f"Hostname '{host}' is already in use by app '{other_app}'"
        ])


def _recipe_pins_hostname(app: App) -> bool:
    """
    True if the staged recipe declares its own usable hostname.

    Mirrors the deploy-time semantics (``Hop3Config.domains`` reads
    ``[domains].list``): only a **non-empty** ``[domains].list`` or a truthy
    ``[env].HOST_NAME`` counts as a pin. An empty ``[domains]`` table (e.g.
    ``list = []`` or only ``_policy``) is NOT a pin — treating it as one would
    suppress the auto-assigned default and leave the app loopback-only.
    """
    hop3_toml = Path(app.src_path) / "hop3.toml"
    if not hop3_toml.is_file():
        return False
    try:
        data = tomllib.loads(hop3_toml.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return False
    domains = data.get("domains")
    if isinstance(domains, dict) and domains.get("list"):
        return True
    env = data.get("env")
    return isinstance(env, dict) and bool(env.get("HOST_NAME"))


def _copy_catalog_source(catalog_app: CatalogApp, app: App) -> None:
    """
    Copy the catalog recipe (hop3.toml + siblings) into the app's src tree.

    Shallow-copies top-level files and directories from the blueprint's verified
    source dir, skipping ``__pycache__`` / ``.git`` at the top level (matching
    the prior controller behaviour exactly). The caller guarantees the source
    dir exists.
    """
    src_path = Path(catalog_app.source_path)
    dest_path = Path(app.src_path)
    dest_path.mkdir(parents=True, exist_ok=True)

    excluded_dirs = {"__pycache__", ".git"}
    for item in src_path.iterdir():
        if item.is_file():
            shutil.copy2(item, dest_path / item.name)
        elif item.is_dir() and item.name not in excluded_dirs:
            shutil.copytree(item, dest_path / item.name, dirs_exist_ok=True)


def _parse_and_add_env_vars(app: App, env_vars_str: str) -> None:
    """
    Append ``K=V`` lines (newline-delimited) to the app's env vars.

    Blank lines, comment lines (leading ``#``), and lines without ``=`` are
    skipped. Append-only (no clear); a freshly created App has no env vars.
    """
    env_vars_str = env_vars_str.strip()
    if not env_vars_str:
        return
    for raw in env_vars_str.split("\n"):
        line = raw.strip()
        if "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if key:
                app.env_vars.append(EnvVar(name=key, value=value))
