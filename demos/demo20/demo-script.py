# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 20: Custom Nix Deployment.

Deploys an app built from a hand-written ``hop3.nix`` expression (the "custom
Nix" path): you author the full Nix expression and Hop3's NixBuilder runs
``nix-build`` and uses the ``$out/hop3/runtime.json`` it produces.

Requires a Nix-enabled server (deploy/test with ``--with nix``).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

TITLE = "Demo 20: Custom Nix Deployment (hand-written hop3.nix)"
DESCRIPTION = """
Demonstrates the custom Nix builder:
  - the app ships a hand-written hop3.nix expression
  - Hop3 runs nix-build and uses $out/hop3/runtime.json
  - a tiny static site served by Python's stdlib http.server
"""

APP_NAME = "demo20"
APP_DIR = Path(__file__).parent / "app"
REQUIRES: list[str] = []  # needs a Nix-enabled server (--with nix)
FEATURES = {"extra:nix-custom"}


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

    print_header("Custom Nix Deployment")
    show_file_content(
        APP_DIR / "hop3.nix",
        "Hand-written Nix expression (hop3.nix):",
        max_lines=30,
    )
    pause(ctx.pause_between_steps)

    # Deploy: NixBuilder runs `nix-build` on the hand-written expression.
    deploy_app(ctx, APP_NAME, APP_DIR)
    set_hostname(ctx, APP_NAME, app_hostname)
    redeploy_app(ctx, APP_NAME, APP_DIR)

    # Nix closures can take a while to realise on a cold store.
    wait_for_app_ready(APP_NAME, timeout=120.0)
    wait_for_app(seconds=2, message="Waiting for nginx to reload...")

    check_app_status(ctx, APP_NAME)

    print_header("Testing Application")
    test_app_via_curl(
        ctx, app_url, expected_content="Hello from a custom Nix deployment"
    )

    cleanup_app(ctx, APP_NAME, app_url)
