# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import nox

PYTHON_VERSIONS = ["3.10", "3.11", "3.12"]

nox.options.reuse_existing_virtualenvs = True


@nox.session
def lint(session: nox.Session) -> None:
    session.install("--no-cache-dir", ".")
    session.install("abilian-devtools")
    session.run("make", "lint", external=True)


@nox.session(python=PYTHON_VERSIONS)
def pytest(session: nox.Session) -> None:
    session.install("--no-cache-dir", ".")
    session.install("pytest")
    session.run("pytest", "--tb=short", "tests", external=True)
