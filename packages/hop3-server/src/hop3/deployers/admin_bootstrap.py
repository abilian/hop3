# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""App admin-account bootstrap (ADR 056).

Turns a recipe's ``[admin]`` section into a real initial admin account:

  1. ``provision_admin_credential`` — at deploy config time, generate the
     password ONCE (CSPRNG, stable across redeploy), resolve the email, persist
     an encrypted ``AppAdminCredential``, and inject the canonical
     ``HOP3_ADMIN_USER`` / ``HOP3_ADMIN_EMAIL`` / ``HOP3_ADMIN_PASSWORD`` env
     vars every deploy from that stored credential.
  2. ``bootstrap_admin_account`` — after the app starts, run the recipe's
     idempotent ``[admin].create`` command once, failing loud on error.
  3. ``read_admin_credential`` / ``reset_admin_credential`` — retrieve or rotate
     the stored credential later.

The stored value is the credential Hop3 *set*; a user who changes it in-app
makes it stale, so callers always present it as the INITIAL credential.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.commands._helpers import parse_hostname_string
from hop3.config import config
from hop3.core.credentials import get_credential_encryptor
from hop3.lib import log
from hop3.orm import AppAdminCredential, AppAdminCredentialRepository

from .env_provisioning import generate_secret_value, set_env_vars

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

    from hop3.orm import App

# Canonical env vars every recipe's `create` command / app reads.
_ENV_USER = "HOP3_ADMIN_USER"
_ENV_EMAIL = "HOP3_ADMIN_EMAIL"
_ENV_PASSWORD = "HOP3_ADMIN_PASSWORD"


class AdminBootstrapError(Exception):
    """A required admin-bootstrap step could not run (fail loud, never skip)."""


def resolve_admin_email(email_spec: str | None) -> str | None:
    """Resolve an ``[admin].email`` spec to a concrete address (or None).

    ``None`` -> no email; ``"operator"`` -> the server's ``OPERATOR_EMAIL``
    (fails loud when unset); any literal -> itself.
    """
    if not email_spec:
        return None
    if email_spec == "operator":
        email = config.OPERATOR_EMAIL
        if not email:
            msg = (
                '[admin].email = "operator" but this server has no operator '
                "email. Set OPERATOR_EMAIL (or ACME_EMAIL) in hop3-server.toml, "
                "or pass the installer's --operator-email."
            )
            raise AdminBootstrapError(msg)
        return email
    return email_spec


def provision_admin_credential(app: App, admin: dict, db_session: Session) -> None:
    """Generate-once the admin credential and inject the canonical env vars.

    Idempotent like ADR 046 generated secrets: the password is generated and the
    record persisted only on first deploy; every deploy re-injects
    ``HOP3_ADMIN_*`` from the stored record so the values stay stable. No-op when
    the recipe declares no ``[admin]``. The credential is surfaced later by
    ``surface_admin_credential`` (guarded by its own ``surfaced`` flag).
    """
    if not admin:
        return

    repo = AppAdminCredentialRepository(session=db_session)
    credential = repo.get_by_app_id(app.id)

    if credential is None:
        username = admin.get("username") or ""
        email = resolve_admin_email(admin.get("email")) or ""
        password = generate_secret_value(
            admin.get("password") or {"generate": "password"}
        )
        encryptor = get_credential_encryptor()
        credential = AppAdminCredential(
            app_id=app.id,
            encrypted_data=encryptor.encrypt({
                "username": username,
                "email": email,
                "password": password,
            }),
            source="generated",
            bootstrapped=False,
        )
        db_session.add(credential)
        db_session.flush()
        log("  Generated an admin credential (shown after deploy)", level=1, fg="green")

    data = get_credential_encryptor().decrypt(credential.encrypted_data)
    injected = {_ENV_PASSWORD: data["password"]}
    if data.get("username"):
        injected[_ENV_USER] = data["username"]
    if data.get("email"):
        injected[_ENV_EMAIL] = data["email"]
    set_env_vars(app, injected, db_session)


def bootstrap_admin_account(
    app: App,
    admin: dict,
    db_session: Session,
    run_create: Callable[[str], None],
) -> None:
    """Run the recipe's ``[admin].create`` command once, after the app deploys.

    ``run_create(command)`` executes the command in the app's runtime (with the
    injected ``HOP3_ADMIN_*`` env) and RAISES on a non-zero exit. Guarded by the
    stored credential's ``bootstrapped`` flag so a redeploy never re-runs it;
    the command must also be idempotent (create-if-absent) as defense in depth.
    A failure aborts loudly — a running app the operator can't log into is not a
    successful deploy.
    """
    create_cmd = admin.get("create")
    if not create_cmd:
        return  # the app bootstraps itself from the injected HOP3_ADMIN_* vars

    repo = AppAdminCredentialRepository(session=db_session)
    credential = repo.get_by_app_id(app.id)
    if credential is None or credential.bootstrapped:
        return

    log(f"  Creating the initial admin account for '{app.name}'...", level=1)
    try:
        run_create(create_cmd)
    except Exception as e:
        msg = (
            f"Admin-account bootstrap failed for '{app.name}': {e}. The app is "
            "running but has no admin account. Fix the [admin].create command "
            "and redeploy."
        )
        raise AdminBootstrapError(msg) from e

    credential.bootstrapped = True
    db_session.add(credential)
    db_session.commit()
    log(f"  ✓ Admin account created for '{app.name}'", level=1, fg="green")


def read_admin_credential(app: App, db_session: Session) -> dict | None:
    """Decrypt and return the stored admin credential, or None.

    Returns ``{"username", "email", "password", "created_at", "source"}``. The
    password is the INITIAL one — the caller must label it as such.
    """
    repo = AppAdminCredentialRepository(session=db_session)
    credential = repo.get_by_app_id(app.id)
    if credential is None:
        return None
    data = get_credential_encryptor().decrypt(credential.encrypted_data)
    data["created_at"] = credential.created_at
    data["source"] = credential.source
    return data


def format_admin_credential(app_name: str, host_name: str, cred: dict) -> str:
    """Render an app's initial admin credential as an operator-facing block."""
    hosts = parse_hostname_string(host_name)
    if hosts and hosts[0] != "_":
        url = f"https://{hosts[0]}/"
    else:
        url = "(no public URL — reachable only on its loopback port)"
    lines = [f"Admin account for '{app_name}'", f"  URL:      {url}"]
    if cred.get("username"):
        lines.append(f"  Username: {cred['username']}")
    if cred.get("email"):
        lines.append(f"  Email:    {cred['email']}")
    lines.append(f"  Password: {cred['password']}")
    created = cred.get("created_at")
    when = created.strftime("%Y-%m-%d") if created else "install"
    lines.append("")
    lines.append(
        f"  This is the INITIAL password (set {when}); it is stale if changed "
        f"in-app.\n  Retrieve later: hop3 app credentials --app {app_name}"
    )
    return "\n".join(lines)


def surface_admin_credential(app: App, db_session: Session) -> None:
    """Print the credential block into the deploy log once, ever (ADR 056).

    Guarded by the credential's own ``surfaced`` flag rather than "was it created
    this deploy", so it fires on the first SUCCESSFUL deploy even when the
    install deploy that created the credential later failed and was retried — and
    never re-prints the password on a subsequent redeploy.
    """
    repo = AppAdminCredentialRepository(session=db_session)
    credential = repo.get_by_app_id(app.id)
    if credential is None or credential.surfaced:
        return

    data = get_credential_encryptor().decrypt(credential.encrypted_data)
    data["created_at"] = credential.created_at
    host_name = app.get_runtime_env().get("HOST_NAME", "")
    block = format_admin_credential(app.name, host_name, data)
    log("", level=0)
    for line in block.splitlines():
        log(line, level=0, fg="cyan")

    credential.surfaced = True
    db_session.add(credential)
    db_session.commit()
