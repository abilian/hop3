# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""ACME / Let's Encrypt setup."""

from __future__ import annotations

from hop3_installer.common import (
    Spinner,
    print_info,
    print_success,
    print_warning,
    run_cmd,
)

from .config import HOME_DIR, ServerInstallerConfig
from .user import run_as_hop3


def setup_acme(config: ServerInstallerConfig) -> None:
    """Install acme.sh for Let's Encrypt."""
    if config.skip_acme:
        print_info("Skipping ACME setup (--skip-acme)")
        return

    acme_sh = HOME_DIR / ".acme.sh" / "acme.sh"

    if acme_sh.exists():
        print_info("acme.sh already installed")
        return

    with Spinner("Installing acme.sh..."):
        run_as_hop3(
            "curl -fsSL https://raw.githubusercontent.com/Neilpang/acme.sh/master/acme.sh -o /tmp/acme.sh"
        )
        run_as_hop3("cd /tmp && bash acme.sh --install")
        run_cmd(["rm", "-f", "/tmp/acme.sh"])

    if acme_sh.exists():
        run_as_hop3(f"bash {acme_sh} --set-default-ca --server letsencrypt")
        print_success("acme.sh installed and configured")
    else:
        print_warning("acme.sh installation may have failed")
