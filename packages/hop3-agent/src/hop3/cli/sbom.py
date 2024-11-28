# Copyright (c) 2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands to generate SBOMs."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from .base import command

if TYPE_CHECKING:
    from hop3.core.app import App


@command
class SbomCmd:
    """Generate a SBOM for an app."""

    def run(self, app: App) -> None:
        cwd = app.virtualenv_path

        subprocess.run(
            "/usr/bin/env",
            shell=True,
            check=True,
            env={},
        )
        subprocess.run(
            f"{cwd}/bin/python -c 'import os; print(os.getcwd())'",
            shell=True,
            check=True,
            cwd=cwd,
            env={},
        )

        subprocess.run(
            f"{cwd}/bin/python -m pip list --format=freeze",
            shell=True,
            check=True,
            cwd=cwd,
            env={},
        )

        subprocess.run(
            f"{cwd}/bin/python -m pip list --format=freeze > /tmp/requirements-prod.txt",
            shell=True,
            check=True,
            env={},
        )
        # print(Path("/tmp/requirements-prod.txt").read_text())
