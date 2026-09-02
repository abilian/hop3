# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
The Hop3-owned probe account an app's smoke test signs in as ([probe]).

Why a second account at all: the [admin] credential is handed to the operator,
so Hop3 stops owning it the moment they change the password. A later sign-in
failure then means either the app broke or the password moved, and from outside
those are the same observation — a check that cannot tell them apart is a check
that cries wolf. Nobody else uses the probe account, so a failed probe sign-in
means the app broke, full stop.

Why not test it unauthenticated instead: a login page renders perfectly with a
dead database, and for some apps is not even dynamic. Signing in is what
traverses app code, session, database and password verification — the whole
stack the operator actually depends on.

The password lives in the app's runtime env as an ADR-046 generated secret
rather than in the encrypted credential store: it is Hop3's own, grants no
administrator rights, and sits beside DATABASE_URL, which is strictly more
sensitive. That also makes it rotatable — nothing human depends on it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.lib import log
from hop3.lib.logging import server_log

from .env_provisioning import generate_secret_value, set_env_vars

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

    from hop3.orm import App

_ENV_USER = "HOP3_PROBE_USER"
_ENV_EMAIL = "HOP3_PROBE_EMAIL"
_ENV_PASSWORD = "HOP3_PROBE_PASSWORD"

#: Marks that the probe account exists, so a redeploy does not re-create it and
#: the smoke test may sign in as it. Public because `checks.runner` reads it —
#: one definition, not the two it used to have.
#:
#: Written in exactly one place: after ``[probe].create`` has run and exited 0.
#: Nothing else may claim an account exists.
PROBE_CREATED_ENV = "HOP3_PROBE_CREATED"

DEFAULT_USERNAME = "hop3probe"


class ProbeAccountError(Exception):
    """The probe account could not be created (fail loud, never skip)."""


def provision_probe_credential(app: App, probe: dict, db_session: Session) -> None:
    """
    Generate-once the probe password and inject the canonical env vars.

    Idempotent like every ADR-046 generated secret: minted on the first deploy
    that declares [probe], then re-injected unchanged. No-op when the app
    declares no [probe] — that app opted out, and its check verifies the
    handover only.
    """
    if not probe:
        return

    runtime_env = app.get_runtime_env()
    password = runtime_env.get(_ENV_PASSWORD) or generate_secret_value({
        "generate": "password",
        "length": 24,
    })

    injected = {
        _ENV_USER: probe.get("username") or DEFAULT_USERNAME,
        _ENV_PASSWORD: password,
    }
    email = probe.get("email")
    if email:
        injected[_ENV_EMAIL] = email

    set_env_vars(app, injected, db_session)


def bootstrap_probe_account(
    app: App,
    probe: dict,
    db_session: Session,
    run_create: Callable[[str], None],
) -> None:
    """
    Run the recipe's ``[probe].create`` command once, after the app deploys.

    Mirrors the admin bootstrap: ``run_create(command)`` executes in the app's
    runtime with the injected ``HOP3_PROBE_*`` and RAISES on a non-zero exit.

    A failure aborts loudly rather than leaving the app unverifiable in silence.
    The command must also be idempotent (create-if-absent) as defence in depth,
    since the guard below is an env var an operator could clear.
    """
    if not probe:
        return

    create_cmd = probe.get("create")
    if not create_cmd:
        # The recipe says the app creates this account itself from the injected
        # HOP3_PROBE_*. Hop3 has no way to confirm it did, so it does NOT set
        # the marker — and the check therefore never signs in as an account
        # whose existence nobody established.
        #
        # This was briefly written the other way, marking such a probe created
        # so the check would use it. Both apps that rely on it (matomo,
        # uptime-kuma) then failed against accounts their own bootstraps were
        # supposed to have made. The marker means "this exists"; only the branch
        # below can honestly write it.
        return

    if app.get_runtime_env().get(PROBE_CREATED_ENV):
        return

    log("  Creating the Hop3 probe account...", level=1, fg="blue")
    try:
        run_create(create_cmd)
    except Exception as e:
        # Loud, but NOT fatal. The probe exists to verify the app; it is not
        # part of it. Failing the deploy here would take a working app down
        # because a test account could not be made — and would make the
        # platform's own diagnostics a deployment dependency.
        #
        # Nothing is silently skipped: this is reported here, and the smoke
        # test then falls back to the operator's credential and SAYS it did
        # ("verified the handover only"), so the weaker claim is never
        # mistaken for the full one.
        log(
            f"  Could not create the probe account for '{app.name}': {e}",
            level=0,
            fg="yellow",
        )
        log(
            "  The app is unaffected, but its smoke test can only verify the "
            "operator's credential — which stops being Hop3's to assert once "
            "they change the password.",
            level=1,
            fg="yellow",
        )
        server_log.warning(
            "probe account creation failed", app_name=app.name, error=str(e)
        )
        return

    verify_cmd = probe.get("verify")
    if verify_cmd:
        try:
            run_create(verify_cmd)
        except Exception as e:
            # The marker means "this account exists". `create` exiting 0 is the
            # app CLI's claim, not evidence (Gitea/Forgejo print an error and
            # exit 0 for a reserved name). With verify declared and failing, we
            # know the claim is false, so the marker must not be written —
            # otherwise the smoke test signs in as an account that isn't there
            # and reports the app broken for the wrong reason.
            log(
                f"  Probe account for '{app.name}' could not be verified "
                f"([probe].create exited 0 but [probe].verify failed: {e}); "
                f"the smoke test will fall back to the operator credential.",
                level=0,
                fg="yellow",
            )
            server_log.warning(
                "probe account verification failed",
                app_name=app.name,
                error=str(e),
            )
            return

    set_env_vars(app, {PROBE_CREATED_ENV: "1"}, db_session)
    if verify_cmd:
        log("  Probe account created and verified", level=2, fg="green")
    else:
        log(
            "  Probe account created (unverified: no [probe].verify)",
            level=2,
            fg="green",
        )
