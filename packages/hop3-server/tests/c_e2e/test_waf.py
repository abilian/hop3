# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
E2E: a WAF-enabled app on the full nginx -> LeWAF -> uWSGI path (ADR 050).

Two proofs on a real Docker deploy:
* a WAF-enabled app blocks an SQLi (403) over the real proxy chain while clean
  traffic passes (200);
* a repeat attacker is auto-banned -- after enough blocked requests and a
  reconcile pass, even a clean request from that source is denied (ADR 050 §4).

A green deploy is itself proof the container has the ``waf`` extra installed:
with lewaf absent, ``configure_waf_preflight`` aborts the deploy (fail-closed).
"""

from __future__ import annotations

import subprocess
import time
from typing import TYPE_CHECKING

import httpx
import pytest

from .conftest import cli_env, deploy_flask_app, wait_for_http_ready

if TYPE_CHECKING:
    from pathlib import Path

WAF_HOSTNAME = "waf-demo.test.local"
BAN_HOSTNAME = "waf-ban-demo.test.local"

# The proxy redirects HTTP to HTTPS by DEFAULT, so port 80 answers
# `301 https://<host>/` before a request reaches the WAF at all. The container
# publishes only 22/80/8000 and the vhost name resolves nowhere off it, so that
# redirect leads out of the test entirely. `[deploy].allow-http` is the
# documented opt-out and keeps the chain under test real (nginx -> LeWAF ->
# uWSGI), minus a TLS hop these tests are not about.
#
# It must be set HERE and not as an env var: the deployer writes
# `HOP3_ALLOW_HTTP` from this file on every deploy (deployer.py:1144), so an
# ENV-file value is overwritten with the recipe's default before nginx reads it.
ALLOW_PLAIN_HTTP = """
[deploy]
allow-http = true
"""

# Minimal policy: ``enabled = true`` runs the OWASP CRS (blocks attacks, passes
# clean traffic). ``mode = "block"`` is the default, spelled out for clarity.
WAF_HOP3_TOML = (
    """\
[waf]
enabled = true
mode = "block"
"""
    + ALLOW_PLAIN_HTTP
)

# Same, plus repeat-offender bans with a low threshold so the test trips it fast.
BAN_HOP3_TOML = (
    """\
[waf]
enabled = true
mode = "block"

[waf.bans]
enabled = true
threshold = 3
window = "10m"
duration = "1h"
"""
    + ALLOW_PLAIN_HTTP
)

# Proven SQLi payload from tests/b_integration/waf/test_proxy_integration.py
# (id=1' OR 1=1--, URL-encoded in the query string that the CRS inspects).
SQLI_PATH = "/?id=1%27%20OR%201%3D1--"


def _wait_for_status(url, expected, headers, timeout=30) -> bool:
    """Poll ``url`` until it returns ``expected`` (proxy reloads are async)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if httpx.get(url, headers=headers, timeout=5).status_code == expected:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(1)
    return False


@pytest.mark.e2e
class TestWaf:
    """LeWAF blocks attacks -- and bans repeat offenders -- on a real deploy."""

    def test_waf_blocks_sqli_over_full_path(
        self, hop3_container, test_app_dir: Path, request
    ) -> None:
        app_name = "waf-demo"
        request.node.hop3_container = hop3_container["container"]
        request.node.hop3_app = app_name

        result = deploy_flask_app(
            hop3_container,
            test_app_dir,
            app_name,
            env_vars={"HOST_NAME": WAF_HOSTNAME},
            extra_files={"hop3.toml": WAF_HOP3_TOML},
        )
        # A fail-closed WAF preflight (e.g. lewaf missing) surfaces here.
        assert result.returncode == 0, (
            "WAF app deploy failed -- is the 'waf' extra installed in the "
            f"container?\n--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )

        base = hop3_container["http_base"]
        headers = {"Host": WAF_HOSTNAME}

        # Clean traffic reaches the app through the WAF proxy (200 + body).
        ready, err = wait_for_http_ready(
            f"{base}/", 200, "Hello from Flask!", headers=headers, timeout=90
        )
        assert ready, f"WAF-fronted app never served clean traffic: {err}"

        # An SQLi in the query string is denied by the CRS before the app.
        blocked = httpx.get(
            f"{base}{SQLI_PATH}", headers=headers, follow_redirects=False, timeout=10
        )
        assert blocked.status_code == 403, (
            f"WAF did not block SQLi (status {blocked.status_code}); the attack "
            "reached the app instead of being denied at the proxy"
        )
        assert "Hello from Flask!" not in blocked.text  # never reached uWSGI

    def test_repeat_attacker_is_banned(
        self, hop3_container, test_app_dir: Path, request
    ) -> None:
        app_name = "waf-ban-demo"
        request.node.hop3_container = hop3_container["container"]
        request.node.hop3_app = app_name

        result = deploy_flask_app(
            hop3_container,
            test_app_dir,
            app_name,
            env_vars={"HOST_NAME": BAN_HOSTNAME},
            extra_files={"hop3.toml": BAN_HOP3_TOML},
        )
        assert result.returncode == 0, (
            f"ban-demo deploy failed:\n{result.stdout}\n{result.stderr}"
        )

        base = hop3_container["http_base"]
        headers = {"Host": BAN_HOSTNAME}

        ready, err = wait_for_http_ready(
            f"{base}/", 200, "Hello from Flask!", headers=headers, timeout=90
        )
        assert ready, f"ban-demo never served clean traffic: {err}"

        # Trip the ban threshold: several blocked attacks from this source.
        for _ in range(4):
            attack = httpx.get(f"{base}{SQLI_PATH}", headers=headers, timeout=10)
            assert attack.status_code == 403

        # The in-process scorer runs every 60s; trigger it now instead of waiting.
        rec = subprocess.run(
            ["hop3", "waf", "reconcile-bans"],
            env=cli_env(hop3_container),
            capture_output=True,
            text=True,
            errors="replace",  # CLI output may not be valid UTF-8
            check=False,
            timeout=60,
        )
        assert rec.returncode == 0, (
            f"reconcile-bans failed:\n{rec.stdout}\n{rec.stderr}"
        )

        # Now the source is banned: even a CLEAN request is denied (403). The
        # proxy reload after reconcile is async, so poll until it takes effect.
        assert _wait_for_status(f"{base}/", 403, headers, timeout=30), (
            "repeat attacker was not banned after reconcile "
            "(clean request still served)"
        )
