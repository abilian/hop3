# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Email backend pre-stage (`--with email`): install Postfix, inert.

Only makes the package present — it never writes ``main.cf``, sets a relayhost,
or starts an MTA. Backend selection configures the loopback relay later via the
hop3-rootd ``postfix.configure`` op (ADR 054). On Debian the debconf
"No configuration" preseed stops apt from writing a default Internet-Site MTA
that would bind public port 25.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from hop3_installer.common import (
    CommandError,
    InstallStepError,
    Spinner,
    cmd_exists,
    print_success,
    run_cmd,
)

# Local copy (deps_common imports this module → importing back would cycle).
_APT_ENV = {"DEBIAN_FRONTEND": "noninteractive", "NEEDRESTART_MODE": "a"}

# Preseed so postfix installs without prompting and without a working MTA
# config — Hop3 owns main.cf, written later by the rootd op.
_DEBCONF_PRESEED = "postfix postfix/main_mailer_type select No configuration\n"


def pre_stage_email() -> None:
    """Install Postfix inert for the email loopback relay (ADR 054)."""
    if cmd_exists("apt-get"):
        _pre_stage_debian()
    elif cmd_exists("dnf"):
        _pre_stage_fedora()
    else:
        msg = "--with email: no apt-get or dnf to install Postfix with"
        raise InstallStepError(msg)


def _pre_stage_debian() -> None:
    # Preseed BEFORE apt, or Debian writes a default Internet-Site MTA on :25.
    with tempfile.NamedTemporaryFile(
        "w", suffix=".seed", delete=False, encoding="utf-8"
    ) as f:
        f.write(_DEBCONF_PRESEED)
        seed_path = f.name
    try:
        run_cmd(["debconf-set-selections", seed_path], env=_APT_ENV)
        with Spinner("Installing Postfix + opendkim (email relay)..."):
            # opendkim/opendkim-tools back the direct backend's DKIM signing;
            # they stay inert until `server email backend direct` configures them.
            result = run_cmd(
                ["apt-get", "install", "-y", "postfix", "opendkim", "opendkim-tools"],
                env=_APT_ENV,
                check=False,
            )
    finally:
        Path(seed_path).unlink(missing_ok=True)
    _report(result)


def _pre_stage_fedora() -> None:
    with Spinner("Installing Postfix + opendkim (email relay)..."):
        result = run_cmd(["dnf", "install", "-y", "postfix", "opendkim"], check=False)
    _report(result)


def _report(result: subprocess.CompletedProcess) -> None:
    """
    Report the install outcome; a failure stops the install.

    It used to warn and leave the failure to the moment an email backend was
    selected, on a server that had reported `--with email` as installed.
    """
    if result.returncode != 0:
        raise CommandError(
            cmd=["install", "postfix", "opendkim"],
            returncode=result.returncode,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
        )
    print_success("Postfix installed (inert; configured on email-backend selection)")
