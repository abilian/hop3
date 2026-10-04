# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""ACME / Let's Encrypt setup."""

from __future__ import annotations

from hop3_installer.common import (
    InstallStepError,
    Spinner,
    print_info,
    print_success,
    run_cmd,
)
from hop3_installer.constants import HOME_DIR

from .config import ServerInstallerConfig
from .user import run_as_hop3, run_as_hop3_shell


def setup_acme(config: ServerInstallerConfig) -> None:
    """Install acme.sh for Let's Encrypt."""
    if config.skip_acme:
        print_info("Skipping ACME setup (--skip-acme)")
        return

    acme_sh = HOME_DIR / ".acme.sh" / "acme.sh"

    if acme_sh.exists():
        print_info("acme.sh already installed")
        return

    # Each step raises with its output: their results were ignored, and a
    # failure surfaced as "acme.sh installation may have failed", then as
    # every Let's Encrypt issuance failing at app deploy.
    with Spinner("Installing acme.sh..."):
        run_as_hop3(
            ["curl", "-fsSL",
             "https://raw.githubusercontent.com/Neilpang/acme.sh/master/acme.sh",
             "-o", "/tmp/acme.sh"],
            check=True,
        )  # fmt: skip
        run_as_hop3_shell("cd /tmp && bash acme.sh --install", check=True)
        run_cmd(["rm", "-f", "/tmp/acme.sh"])

    if not acme_sh.exists():
        msg = f"acme.sh --install succeeded, but {acme_sh} does not exist"
        raise InstallStepError(msg)
    run_as_hop3(
        ["bash", str(acme_sh), "--set-default-ca", "--server", "letsencrypt"],
        check=True,
    )
    print_success("acme.sh installed and configured")
