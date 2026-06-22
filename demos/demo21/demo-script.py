# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 21: Templated Nix Deployment.

Deploys an app via a [nix] template (the "templated Nix" path): instead of
hand-writing a Nix expression, the app declares a few TOML keys and Hop3's
nix-gen generates the hop3.nix from a template (here ``nixpkgs-wrapper``).

Requires a Nix-enabled server (deploy/test with ``--with nix``).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

TITLE = "Demo 21: Templated Nix Deployment (nixpkgs-wrapper template)"
DESCRIPTION = """
Demonstrates the templated Nix builder:
  - the app declares a [nix] template in hop3.toml (no hand-written Nix)
  - Hop3's nix-gen generates the hop3.nix from the nixpkgs-wrapper template
  - a stock nixpkgs package (python3) serves a static page
"""

APP_NAME = "demo21"
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

    print_header("Templated Nix Deployment")
    show_file_content(
        APP_DIR / "hop3.toml",
        "Declarative [nix] template config (hop3.toml):",
        max_lines=30,
    )
    pause(ctx.pause_between_steps)

    # Deploy: nix-gen renders the template to hop3.nix, then NixBuilder builds it.
    deploy_app(ctx, APP_NAME, APP_DIR)
    set_hostname(ctx, APP_NAME, app_hostname)
    redeploy_app(ctx, APP_NAME, APP_DIR)

    # Nix closures can take a while to realise on a cold store.
    wait_for_app_ready(APP_NAME, timeout=120.0)
    wait_for_app(seconds=2, message="Waiting for nginx to reload...")

    check_app_status(ctx, APP_NAME)

    print_header("Testing Application")
    test_app_via_curl(
        ctx, app_url, expected_content="Hello from a templated Nix deployment"
    )

    cleanup_app(ctx, APP_NAME, app_url)
