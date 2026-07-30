# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Run an app's ``check.py`` smoke test.

One implementation, shared by `hop3 app check` and the end of every deploy, so
a green result means the same thing however it was produced. Running it at the
end of a deploy is the point: deploying proves an app STARTS, and today's
failures showed repeatedly that this is not the same as it working — apps
served a login page perfectly while rejecting every credential.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from hop3.deployers.admin_bootstrap import read_admin_credential
from hop3.deployers.probe_account import PROBE_CREATED_ENV
from hop3.lib.logging import server_log
from hop3.server.checks._helper import BROWSER_REQUIRED_MARKER

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from hop3.orm import App

#: A smoke test signs in and fetches a page or two; beyond this it is hung, and
#: neither an RPC call nor a deploy may wait on it forever.
CHECK_TIMEOUT = 180


@dataclass(frozen=True)
class CheckOutcome:
    """What running an app's check.py produced."""

    #: False only when the check ran and failed. An app with no check.py did not
    #: fail — it simply has nothing to verify, which `ran` distinguishes.
    passed: bool
    ran: bool
    output: str
    #: False when the app declares no [probe] and the check had to sign in with
    #: the OPERATOR's credential. That still verifies the handover, but stops
    #: being Hop3's to assert once they change the password — so a green result
    #: there is a weaker claim and must not be reported as an equal one.
    used_hop3_account: bool = True
    #: The app declared its sign-in undrivable over HTTP (a JavaScript-rendered
    #: admin UI). Everything reachable was checked; the sign-in itself is
    #: verified by the browser harness instead.
    needs_browser: bool = False

    @property
    def summary(self) -> str:
        if not self.ran:
            return "no check.py — nothing was verified"
        if not self.passed:
            return "smoke test FAILED"
        if self.needs_browser:
            return (
                "smoke test passed, but the SIGN-IN was not verified here — "
                "this app's admin UI needs a browser; the browser harness "
                "covers it"
            )
        if not self.used_hop3_account:
            return "smoke test passed (verified the handover only — no [probe])"
        return "smoke test passed"


#: The variables that tell a check a probe account is available to sign in as.
_PROBE_VARS = ("HOP3_PROBE_USER", "HOP3_PROBE_EMAIL", "HOP3_PROBE_PASSWORD")


def _drop_uncreated_probe(env: dict[str, str], app_name: str) -> None:
    """
    Hide the probe credential from the check unless the account exists.

    `HOP3_PROBE_*` is injected whenever a recipe declares `[probe]`, because the
    recipe's own `create` command needs those values to make the account. If
    that command then FAILS, the variables remain — and `Check.has_probe`, which
    reads the password, went on reporting a probe was available. The check duly
    signed in as an account nobody had created and failed, reporting the
    application broken when the application was fine.

    Mattermost showed it plainly: `mmctl --local` needs a socket its config does
    not enable, the probe was never created, and the check got a 401 from an app
    whose administrator credential works perfectly.

    The probe bootstrap already records success (`HOP3_PROBE_CREATED`); nothing
    consulted it. With the variables removed the check falls back to the
    operator's credential and says which account it used — the behaviour
    `bootstrap_probe_account` has always documented but never had.
    """
    if env.get(PROBE_CREATED_ENV):
        return
    if not any(env.get(name) for name in _PROBE_VARS):
        return
    server_log.info(
        "probe account was not created; check falls back to the admin credential",
        app_name=app_name,
    )
    for name in _PROBE_VARS:
        env.pop(name, None)


def run_app_check(app: App, db_session: Session) -> CheckOutcome:
    """
    Execute the app's ``check.py``, if it ships one.

    The check runs under the server's own interpreter (so it can import
    ``hop3.server.checks``) from the app's source tree, and receives the app's
    runtime env plus the credential `hop3 app credentials` would show an
    operator. If those two could differ, a passing test would not be testing
    what the operator is handed.
    """
    script = Path(app.src_path) / "check.py"
    if not script.exists():
        return CheckOutcome(passed=True, ran=False, output="")

    host = app.get_runtime_env().get("HOST_NAME", "").split()
    hostname = host[0] if host else "localhost"

    # The app's runtime env already carries HOP3_PROBE_* (an ADR-046 generated
    # secret), so the check can sign in as the account Hop3 still owns.
    env = dict(os.environ)
    env.update(app.get_runtime_env())
    _drop_uncreated_probe(env, app.name)
    cred = read_admin_credential(app, db_session)
    if cred:
        env["HOP3_ADMIN_USER"] = cred.get("username", "")
        env["HOP3_ADMIN_EMAIL"] = cred.get("email", "")
        env["HOP3_ADMIN_PASSWORD"] = cred.get("password", "")

    try:
        result = subprocess.run(
            [sys.executable, str(script), hostname, "443"],
            check=False,
            capture_output=True,
            text=True,
            timeout=CHECK_TIMEOUT,
            cwd=str(app.src_path),
            env=env,
        )
    except subprocess.TimeoutExpired:
        # A hung check is a failure, never a pass: whatever it was waiting for
        # never arrived, which is exactly what it exists to detect.
        return CheckOutcome(
            passed=False,
            ran=True,
            output=f"check.py did not finish within {CHECK_TIMEOUT}s",
        )

    output = (result.stdout + result.stderr).strip()
    return CheckOutcome(
        passed=result.returncode == 0,
        ran=True,
        output=output,
        used_hop3_account=bool(env.get("HOP3_PROBE_PASSWORD")),
        needs_browser=BROWSER_REQUIRED_MARKER in output,
    )
