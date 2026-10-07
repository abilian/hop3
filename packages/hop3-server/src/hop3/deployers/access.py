# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Deploy-time wiring for the access gate (ADR 062).

Runs before the build, beside the WAF preflight. A gated app is refused when
something the gate relies on is missing (§5), then its policy is recorded on
the app, where the proxy's check reads it on every request. It is committed at
once: the check runs in another session, and a proxy config that names a gate
the database does not know answers 503 until it does.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3 import config as c
from hop3.core.plugins import get_proxy_class
from hop3.lib import Diagnosis, abort_with_diagnosis, log

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from hop3.orm import App
    from hop3.project.config import AppConfig


def configure_access_preflight(
    app: App, app_config: AppConfig, db_session: Session | None
) -> None:
    """Refuse a gate the server cannot enforce; record the app's policy."""
    section = app_config.hop3_config.access
    if section.require == "none":
        app.access_role = None
        app.access_public_paths = []
    else:
        _refuse_unenforceable_gate(app, allow_http=app_config.hop3_config.allow_http)
        app.access_role = section.role
        app.access_public_paths = list(section.public_paths)
        log(
            f"Access gate on '{app.name}': signed-in accounts with role "
            f"{section.role.value} or above"
            + (
                f"; public: {', '.join(section.public_paths)}"
                if section.public_paths
                else ""
            ),
            level=1,
            fg="green",
        )
    if db_session is not None:
        db_session.commit()


def _refuse_unenforceable_gate(app: App, *, allow_http: bool) -> None:
    host = app.get_runtime_env().get("HOST_NAME", "")
    reasons = {
        "no admin domain is set, so there is nowhere to sign in": not c.config.ADMIN_DOMAIN,
        "the app has no hostname, so it has no certificate and no cookie scope": (
            not host or host == "_"
        ),
        "[deploy].allow-http serves the app over plain HTTP, where the gate's "
        "Secure cookie is never sent": allow_http,
        f"this server's proxy ({c.HOP3_PROXY_TYPE}) cannot enforce it": (
            not get_proxy_class().gates_access
        ),
    }
    for reason, applies in reasons.items():
        if applies:
            abort_with_diagnosis(
                Diagnosis(
                    component="Access gate",
                    action=f"put '{app.name}' behind a sign-in",
                    reason=reason,
                    hint=(
                        'fix the cause, or remove [access] require = "auth" '
                        "from hop3.toml to publish the app without a gate"
                    ),
                )
            )
