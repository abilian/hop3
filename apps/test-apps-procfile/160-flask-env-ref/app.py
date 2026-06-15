"""Flask test app proving Hop3 dynamic [env] references (ADR 046 §1b).

`hop3.toml` declares two references:

    DB_HOST_VIA_REF  = { from = "db", key = "PGHOST" }   # addon reference
    APP_NAME_VIA_REF = { key = "name" }                  # app fact

The postgres addon also auto-injects ``PGHOST`` directly, so a correctly
resolved reference makes ``DB_HOST_VIA_REF == PGHOST``. The app serves
"ENV REF OK" only when both references resolved — the addon ref matches the
independently-injected value, and the app-fact ref is non-empty. This proves
the feature end-to-end through the real deploy pipeline, not just in unit tests.
"""

from __future__ import annotations

import os

from flask import Flask

app = Flask(__name__)


@app.route("/")
def index() -> tuple[str, int]:
    """Pass only if both references resolved correctly."""
    pghost = os.environ.get("PGHOST", "")
    db_host_ref = os.environ.get("DB_HOST_VIA_REF", "")
    name_ref = os.environ.get("APP_NAME_VIA_REF", "")

    problems = []
    if not pghost:
        problems.append("PGHOST not injected (postgres addon missing?)")
    if not db_host_ref or db_host_ref != pghost:
        problems.append(
            f"addon ref mismatch: DB_HOST_VIA_REF={db_host_ref!r} != PGHOST={pghost!r}"
        )
    if not name_ref:
        problems.append("app-fact ref empty: APP_NAME_VIA_REF did not resolve")

    if problems:
        return "ENV REF FAILED: " + "; ".join(problems), 500
    return "ENV REF OK", 200


@app.route("/config")
def config() -> tuple[str, int]:
    """Echo the resolved values for inspection (no secrets — these are hosts/names)."""
    body = (
        f"PGHOST={os.environ.get('PGHOST', '')}\n"
        f"DB_HOST_VIA_REF={os.environ.get('DB_HOST_VIA_REF', '')}\n"
        f"APP_NAME_VIA_REF={os.environ.get('APP_NAME_VIA_REF', '')}\n"
    )
    return body, 200
