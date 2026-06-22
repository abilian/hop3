# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 22: Flask App via Templated Nix.

Deploys a real Flask web app through the python-venv [nix] template (the
"templated Nix" path applied to a framework app): the dependencies are
pip-installed into a Nix-built virtualenv and the local app.py is run under
gunicorn — no hand-written Nix expression.

Complements demo21 (templated Nix wrapping a stock package) by showing the
templated path for an application with its own source code.

Requires a Nix-enabled server (deploy/test with ``--with nix``).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

TITLE = "Demo 22: Flask App via Templated Nix (python-venv)"
DESCRIPTION = """
Demonstrates the templated Nix builder for a framework app:
  - a Flask app (home page + /api/info JSON endpoint) with local app.py
  - the python-venv [nix] template pip-installs Flask + gunicorn into a Nix venv
  - gunicorn runs the local app.py — no hand-written Nix expression
"""

APP_NAME = "demo22"
APP_DIR = Path(__file__).parent / "app"
REQUIRES: list[str] = []  # needs a Nix-enabled server (--with nix)
FEATURES = {"extra:nix-templated"}


def run(ctx: DemoContext) -> None:
    """Run the demo."""
    from lib import (
        check_app_status,
        cleanup_app,
        deploy_app,
        pause,
        print_header,
        redeploy_app,
        set_hostname,
        show_file_content,
        test_app_via_curl,
        wait_for_app,
        wait_for_app_ready,
    )

    app_hostname = ctx.get_app_hostname(APP_NAME)
    app_url = f"https://{app_hostname}"

    print_header("Flask App via Templated Nix")
    show_file_content(
        APP_DIR / "hop3.toml",
        "Declarative python-venv [nix] template config (hop3.toml):",
        max_lines=30,
    )
    show_file_content(APP_DIR / "app.py", "The Flask app (app.py):", max_lines=20)
    pause(ctx.pause_between_steps)

    # Deploy: nix-gen renders the python-venv template; NixBuilder builds the
    # venv (pip install) and Hop3 runs the local app.py via the generated worker.
    deploy_app(ctx, APP_NAME, APP_DIR)
    set_hostname(ctx, APP_NAME, app_hostname)
    redeploy_app(ctx, APP_NAME, APP_DIR)

    # Nix venv builds (pip install) can take a while on a cold store.
    wait_for_app_ready(APP_NAME, timeout=180.0)
    wait_for_app(seconds=2, message="Waiting for nginx to reload...")

    check_app_status(ctx, APP_NAME)

    print_header("Testing the Flask App")
    test_app_via_curl(ctx, app_url, expected_content="Hello from demo22")
    test_app_via_curl(ctx, f"{app_url}/api/info", expected_content="flask")

    cleanup_app(ctx, APP_NAME, app_url)
