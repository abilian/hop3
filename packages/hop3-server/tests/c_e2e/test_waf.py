# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""E2E: a WAF-enabled app blocks attacks over the full nginx -> LeWAF -> uWSGI path.

Deploys a plain Flask app whose ``hop3.toml`` turns on the LeWAF WAF (ADR 050),
then drives HTTP *through nginx* -- not the direct app port, which would bypass
the WAF. A clean request reaches the app (200 + body); an SQLi in the query
string is blocked by the vendored OWASP CRS (403) before it ever reaches uWSGI.

A green deploy is itself proof the container has the ``waf`` extra installed:
with lewaf absent, ``configure_waf_preflight`` aborts the deploy (fail-closed),
so the deploy would return an error here instead of a running app.
"""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING

import httpx
import pytest
from hop3_testing.targets.constants import E2E_TEST_SECRET_KEY, create_test_token

from .conftest import FLASK_APP_CODE, init_git_repo, wait_for_http_ready

if TYPE_CHECKING:
    from pathlib import Path

WAF_HOSTNAME = "waf-demo.test.local"

# Minimal policy: ``enabled = true`` runs the OWASP CRS (blocks attacks, passes
# clean traffic). ``mode = "block"`` is the default, spelled out for clarity.
WAF_HOP3_TOML = """\
[waf]
enabled = true
mode = "block"
"""

# Proven SQLi payload from tests/b_integration/waf/test_proxy_integration.py
# (id=1' OR 1=1--, URL-encoded in the query string that the CRS inspects).
SQLI_PATH = "/?id=1%27%20OR%201%3D1--"


@pytest.mark.e2e
class TestWafBlocksAttacks:
    """LeWAF blocks an attack over the real proxy chain, on a real deploy."""

    def test_waf_blocks_sqli_over_full_path(
        self, hop3_container, test_app_dir: Path, request
    ) -> None:
        app_name = "waf-demo"
        # Opt in to a diagnostic bundle if this fails (ADR 043 §7).
        request.node.hop3_container = hop3_container["container"]
        request.node.hop3_app = app_name

        # A plain Flask app whose hop3.toml enables the WAF; HOST_NAME pins the
        # nginx server_name so we can address it with a known Host header.
        (test_app_dir / "app.py").write_text(FLASK_APP_CODE)
        (test_app_dir / "requirements.txt").write_text("flask>=3.0\n")
        (test_app_dir / "Procfile").write_text(
            "web: flask --app app run --host 0.0.0.0 --port $PORT\n"
        )
        (test_app_dir / "ENV").write_text(f"HOST_NAME={WAF_HOSTNAME}\n")
        (test_app_dir / "hop3.toml").write_text(WAF_HOP3_TOML)

        init_git_repo(test_app_dir)  # `hop3 deploy <dir>` expects a git repo

        # Deploy the local dir via the container's JWT-authenticated HTTP API:
        # `hop3 deploy --app <name> <dir>`. HOP3_NO_INPUT skips the ADR-042
        # confirm prompt in this non-tty run.
        env = os.environ.copy()
        env["HOP3_API_URL"] = hop3_container["api_url"]
        env["HOP3_API_TOKEN"] = create_test_token(secret_key=E2E_TEST_SECRET_KEY)
        env["HOP3_SECRET_KEY"] = E2E_TEST_SECRET_KEY
        env["HOP3_NO_INPUT"] = "1"
        result = subprocess.run(
            ["hop3", "deploy", "--app", app_name, str(test_app_dir)],
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=600,
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
            f"{base}/",
            expected_status=200,
            expected_content="Hello from Flask!",
            headers=headers,
            timeout=90,
        )
        assert ready, f"WAF-fronted app never served clean traffic: {err}"

        # An SQLi in the query string is denied by the CRS before the app.
        blocked = httpx.get(
            f"{base}{SQLI_PATH}",
            headers=headers,
            follow_redirects=False,
            timeout=10,
        )
        assert blocked.status_code == 403, (
            f"WAF did not block SQLi (status {blocked.status_code}); the attack "
            "reached the app instead of being denied at the proxy"
        )
        assert "Hello from Flask!" not in blocked.text  # never reached uWSGI
