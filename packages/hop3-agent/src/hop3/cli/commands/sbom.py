# Copyright (c) 2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""CLI commands to generate SBOMs."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from hop3.cli.registry import command
from hop3 import config as c

if TYPE_CHECKING:
    from hop3.orm import App


@command
class SbomCmd:
    """Generate a SBOM for an app."""

    def run(self, app: App) -> None:
        # POC implementation, to be replaced later
        # Only works for Python now
        venv = app.virtualenv_path
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(
                f"{venv}/bin/pip list --format=freeze > {tmpdir}/requirements.txt",
                shell=True,
                check=True,
                env={},
            )

            cmd = [
                f"{c.HOP3_ROOT}/venv/bin/cyclonedx-py",
                "requirements",
                "-o",
                f"{tmpdir}/sbom-cyclonedx.json",
                f"{tmpdir}/requirements.txt",
            ]
            subprocess.run(cmd, check=True)

            print(Path(f"{tmpdir}/sbom-cyclonedx.json").read_text())
