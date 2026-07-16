# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Environment variable provisioning during deployment.

This module handles injection of environment variables from hop3.toml [env] section.
Values from hop3.toml are treated as defaults - they only create new variables
and never overwrite existing ones (set via config set or addon provisioning).
"""

from __future__ import annotations

import base64
import secrets
import string
import uuid
from typing import TYPE_CHECKING, Any

from hop3.commands._helpers import parse_hostname_string, unset_env_var
from hop3.core.credentials import get_credential_encryptor
from hop3.lib import log
from hop3.lib.logging import server_log
from hop3.orm import AddonCredentialRepository, EnvVar
from hop3.project.schema import GENERATE_KINDS

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.orm import Session

    from hop3.orm.app import App

# App facts addressable by a `{ key = ... }` reference (no `from`).
_APP_FACT_KEYS = frozenset({"domain", "hostname", "name"})

# Default entropy when a generate spec omits `length`: bytes for
# hex/base64/urlsafe, characters for password (uuid ignores length).
_DEFAULT_GENERATE_LENGTHS: dict[str, int] = {
    "hex": 32,
    "base64": 32,
    "urlsafe": 32,
    "password": 24,
}
_PASSWORD_ALPHABET = string.ascii_letters + string.digits


def set_default_env_vars(
    app: App,
    env_config: dict[str, str],
    db_session: Session,
    *,
    env_policy: str = "keep-existing",
) -> None:
    """Set environment variables from hop3.toml [env] section.

    By default, these are treated as defaults: they create new variables but
    never overwrite existing ones. When env_policy is "override", existing
    values are updated to match hop3.toml on every deploy.

    Args:
        app: The application model
        env_config: Dict of env var name -> value from hop3.toml
        db_session: Database session for persistence
        env_policy: "keep-existing" (default) or "override"
    """
    if not env_config:
        return

    defaults_only = env_policy != "override"

    server_log.info(
        "Setting env vars from config",
        app_name=app.name,
        env_var_count=len(env_config),
        policy=env_policy,
    )

    injected_count, skipped_names = set_env_vars(
        app, env_config, db_session, defaults_only=defaults_only
    )

    if injected_count:
        action = "Set" if defaults_only else "Set/updated"
        log(
            f"  {action} {injected_count} env var(s) from hop3.toml",
            level=1,
            fg="green",
        )
    if skipped_names:
        log(
            f"  Skipped {len(skipped_names)} env var(s) already set: "
            f"{', '.join(sorted(skipped_names))} "
            f"(use 'hop3 config set' to update, or set _policy = \"override\" in [env])",
            level=1,
            fg="yellow",
        )


def set_env_vars(
    app: App,
    env_vars: dict[str, str],
    db_session: Session,
    *,
    defaults_only: bool = False,
) -> tuple[int, list[str]]:
    """Set environment variables on an app.

    Args:
        app: The application model
        env_vars: Dict of env var name -> value
        db_session: Database session for persistence
        defaults_only: If True, only create new vars, never overwrite existing ones

    Returns:
        Tuple of (count of env vars set/updated, list of skipped var names)
    """
    count = 0
    skipped: list[str] = []

    for key, value in env_vars.items():
        existing = None
        for env_var in app.env_vars:
            if env_var.name == key:
                existing = env_var
                break

        if existing:
            if defaults_only:
                skipped.append(key)
                continue
            existing.value = str(value)
            count += 1
        else:
            new_var = EnvVar(app_id=app.id, name=key, value=str(value))
            db_session.add(new_var)
            app.env_vars.append(new_var)
            count += 1

    return count, skipped


def set_public_url_env(app: App, db_session: Session) -> None:
    """Expose the app's canonical public URL as ``HOP3_PUBLIC_URL``.

    Derived from the first host of ``HOST_NAME`` each deploy, so recipes can
    reference a single stable variable — e.g.
    ``[env.computed] APP_URL = "${HOP3_PUBLIC_URL}"`` — instead of hand-building
    the URL. Recompute-or-clear (a computed value, never stale): when the app has
    no real hostname (empty / the ``_`` catch-all), a previously-set value is
    removed rather than left pointing at a domain the app no longer serves.

    Called during ``_process_config_dependencies`` right after the
    ``[domains]`` -> ``HOST_NAME`` step, so ``${HOP3_PUBLIC_URL}`` is available to
    both env refs and computed vars in the same deploy.
    """
    host_name = next((ev.value for ev in app.env_vars if ev.name == "HOST_NAME"), "")
    hosts = parse_hostname_string(host_name)
    if hosts and hosts[0] != "_":
        set_env_vars(app, {"HOP3_PUBLIC_URL": f"https://{hosts[0]}"}, db_session)
    else:
        unset_env_var(app, "HOP3_PUBLIC_URL")


def set_computed_env_vars(
    app: App,
    computed_config: dict[str, str],
    db_session: Session,
) -> None:
    """Resolve and set computed environment variables from [env.computed].

    Computed vars use ${VAR} interpolation against the app's current env vars
    (including addon-injected ones). They always overwrite existing values.

    Args:
        app: The application model
        computed_config: Dict of var name -> template string (e.g., "${PGHOST}")
        db_session: Database session for persistence
    """
    if not computed_config:
        return

    from hop3.lib.templating import expand_vars  # noqa: PLC0415

    # Build current env snapshot for interpolation
    current_env = {ev.name: ev.value for ev in app.env_vars}

    resolved: dict[str, str] = {}
    for key, template in computed_config.items():
        value = expand_vars(str(template), current_env)
        # Check for unresolved variables (still contain ${...})
        if "${" in value:
            log(
                f"  WARNING: Unresolved variable in {key} = {template!r} "
                f"(resolved to {value!r}). Check that referenced vars are set.",
                level=0,
                fg="yellow",
            )
        resolved[key] = value

    # Set computed vars (always override — they're derived values)
    count, _ = set_env_vars(app, resolved, db_session, defaults_only=False)

    if count:
        log(
            f"  Set {count} computed env var(s) from [env.computed]",
            level=1,
            fg="green",
        )


def generate_secret_value(spec: Mapping[str, Any]) -> str:
    """Generate one secret value from an [env] ``{ generate = ... }`` spec.

    Pure and CSPRNG-backed (the stdlib ``secrets`` module — never ``random``).
    The schema validates the spec up front, but this also guards the
    ``HOP3_SKIP_CONFIG_VALIDATION`` path: an unknown generator raises rather
    than silently producing nothing (ADR 046).

    Args:
        spec: A generate spec — ``generate`` (required), optional ``length``
            and ``prefix``.

    Returns:
        The generated value, with ``prefix`` prepended when present.
    """
    kind = spec.get("generate")
    if kind not in GENERATE_KINDS:
        msg = (
            f"Unknown [env] generator {kind!r}. "
            f"Must be one of: {', '.join(sorted(GENERATE_KINDS))}."
        )
        raise ValueError(msg)
    kind = str(kind)  # narrowed: a valid generator name past the guard

    length = spec.get("length") or _DEFAULT_GENERATE_LENGTHS.get(kind, 32)

    if kind == "hex":
        body = secrets.token_hex(length)
    elif kind == "base64":
        body = base64.b64encode(secrets.token_bytes(length)).decode("ascii")
    elif kind == "urlsafe":
        body = secrets.token_urlsafe(length)
    elif kind == "password":
        body = "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))
    else:  # uuid
        body = str(uuid.uuid4())

    prefix = spec.get("prefix") or ""
    return f"{prefix}{body}"


def set_generated_env_vars(
    app: App,
    generated_config: dict[str, Any],
    db_session: Session,
) -> None:
    """Materialize [env] generated secrets, once, for vars that are unset.

    Generated-once semantics (ADR 046): a secret is created with a CSPRNG only
    when the var has no value yet, persisted as a normal env var, and never
    regenerated on redeploy — so redeploys stay idempotent and secrets don't
    silently rotate. ``_policy = "override"`` does NOT force rotation; rotate
    explicitly with ``hop3 config unset`` then redeploy.

    Args:
        app: The application model.
        generated_config: Dict of var name -> generate spec (from
            ``Hop3Config.env_generated``).
        db_session: Database session for persistence.
    """
    # Generated-once: only materialize vars that have no value yet, so a
    # redeploy never regenerates (and never rotates) a stored secret.
    existing = {ev.name for ev in app.env_vars}
    pending = {
        name: spec for name, spec in generated_config.items() if name not in existing
    }
    if not pending:
        return

    values = {name: generate_secret_value(spec) for name, spec in pending.items()}
    # Delegate persistence to the shared writer (defaults_only mirrors the
    # never-overwrite guarantee) instead of hand-rolling EnvVar rows.
    set_env_vars(app, values, db_session, defaults_only=True)

    log(
        f"  Generated {len(values)} secret(s): {', '.join(sorted(values))}",
        level=1,
        fg="green",
    )
    for name, spec in pending.items():
        if spec.get("display"):
            log(
                f"  {name} = {values[name]}  [generated — shown once, store it now]",
                level=0,
                fg="yellow",
            )


def resolve_env_refs(
    app: App,
    refs_config: dict[str, Any],
    db_session: Session,
) -> None:
    """Resolve dynamic [env] references against addon and app facts (ADR 046).

    Each ``{ from, key }`` / ``{ key }`` / ``{ external_ip }`` entry is a derived
    value, so (like ``[env.computed]``) it overwrites. Resolution fails loud on
    an unattached addon, an unknown key, or an unsupported reference, aborting
    the deploy rather than producing a wrong value.

    Args:
        app: The application model.
        refs_config: Dict of var name -> reference spec (from
            ``Hop3Config.env_refs``).
        db_session: Database session for addon-credential lookups.
    """
    if not refs_config:
        return

    resolved = {
        name: _resolve_env_ref(app, name, spec, db_session)
        for name, spec in refs_config.items()
    }
    set_env_vars(app, resolved, db_session, defaults_only=False)
    log(
        f"  Resolved {len(resolved)} env reference(s): {', '.join(sorted(resolved))}",
        level=1,
        fg="green",
    )


def _resolve_env_ref(
    app: App, name: str, spec: Mapping[str, Any], db_session: Session
) -> str:
    """Resolve a single reference spec to its value (or raise, loudly)."""
    if spec.get("external_ip"):
        msg = (
            f"[env].{name}: external_ip references are not implemented yet "
            "(ADR 046). Set the value with `hop3 config set` for now."
        )
        raise ValueError(msg)

    key = spec.get("key")
    from_ = spec.get("from")
    if from_:
        return _resolve_addon_ref(app, name, from_, key, db_session)
    return _resolve_app_fact(app, name, key)


def _resolve_addon_ref(
    app: App, name: str, addon_name: str, key: str | None, db_session: Session
) -> str:
    """Copy ``key`` from the credentials of the app's addon ``addon_name``."""
    repo = AddonCredentialRepository(session=db_session)
    # Match within the app's own addons by name (a ref carries no addon type).
    credential = next(
        (c for c in repo.get_by_app_id(app.id) if c.addon_name == addon_name),
        None,
    )
    if credential is None:
        msg = f"[env].{name}: addon {addon_name!r} is not attached to {app.name!r}."
        raise ValueError(msg)

    details = get_credential_encryptor().decrypt(credential.encrypted_data)
    if key not in details:
        available = ", ".join(sorted(details)) or "(none)"
        msg = (
            f"[env].{name}: addon {addon_name!r} exposes no key {key!r}. "
            f"Available keys: {available}."
        )
        raise ValueError(msg)
    return str(details[key])


def _resolve_app_fact(app: App, name: str, key: str | None) -> str:
    """Resolve an app-level fact: ``domain`` / ``hostname`` / ``name``."""
    if key in {"domain", "hostname"}:
        host_name = app.get_runtime_env().get("HOST_NAME", "")
        first = host_name.split()[0] if host_name else ""
        if not first:
            msg = (
                f"[env].{name}: no hostname is set for {app.name!r} yet. "
                "Declare [domains] or set HOST_NAME before referencing it."
            )
            raise ValueError(msg)
        return first
    if key == "name":
        return app.name

    known = ", ".join(sorted(_APP_FACT_KEYS))
    msg = f"[env].{name}: unknown app fact {key!r}. Known facts: {known}."
    raise ValueError(msg)
