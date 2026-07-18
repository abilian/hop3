# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Read an app's generated admin credential via the `hop3` CLI (ADR 056)."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class Credential:
    url: str
    username: str
    email: str
    password: str


def read_generated_credential(app_name: str) -> Credential:
    """Parse `hop3 app credentials --app <app>` into its fields (fail loud).

    Uses whatever server the local `hop3` CLI is authenticated against.
    """
    proc = subprocess.run(
        ["hop3", "app", "credentials", "--app", app_name],
        capture_output=True,
        text=True,
        check=False,
    )
    out = (proc.stdout + proc.stderr).strip()
    first = out.splitlines()[0] if out else "(no output)"

    # Keep each message's FIRST line self-explanatory (the caller shows only that
    # line) — never a bare "failed:". A missing app is checked first: the command
    # may report it with exit 0 or non-zero depending on the build.
    if "not found" in out.lower():
        msg = (
            f"{app_name}: not deployed (App not found). "
            "Run `hop3-tools catalog verify --deploy` to install it first."
        )
        raise RuntimeError(msg)
    if proc.returncode != 0:
        msg = f"{app_name}: `hop3 app credentials` failed: {first}"
        raise RuntimeError(msg)
    if "no Hop3-managed admin credential" in out:
        msg = f"{app_name}: no admin credential (recipe missing [admin]?)"
        raise RuntimeError(msg)

    def grab(label: str) -> str:
        m = re.search(rf"^\s*{label}:\s*(.+?)\s*$", out, re.MULTILINE)
        return m.group(1).strip() if m else ""

    url = grab("URL")
    password = grab("Password")
    if not url.startswith("http") or not password:
        msg = f"{app_name}: could not parse credentials output: {first}"
        raise RuntimeError(msg)
    return Credential(
        url=url.rstrip("/"),
        username=grab("Username"),
        email=grab("Email"),
        password=password,
    )
