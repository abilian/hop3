# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import nox

# Minimal version is 3.10
PYTHON_VERSIONS = ["3.10", "3.11", "3.12"]

SUB_REPOS = [
    "packages/hop3-agent",
    "packages/hop3-server",
    "packages/hop3-cli",
    "packages/hop3-testing",
]

nox.options.default_venv_backend = "uv|virtualenv"


nox.options.sessions = [
    "lint",
    "pytest",
]


@nox.session
def lint(session: nox.Session) -> None:
    session.install(".")
    session.install("abilian-devtools")
    session.run("make", "lint", external=True)


@nox.session(python=PYTHON_VERSIONS)
def pytest(session: nox.Session) -> None:
    session.install(".")
    session.install("pytest")
    session.run("pytest")


@nox.session(python=PYTHON_VERSIONS)
@nox.parametrize("sub_repo", SUB_REPOS)
def pytest_packages(session: nox.Session, sub_repo: str) -> None:
    run_subsession(session, sub_repo)


@nox.session
def audit(session: nox.Session) -> None:
    session.run("uv", "pip", "install", ".")
    session.run("uv", "pip", "install", "safety", "pip-audit")
    session.run("pip-audit")
    session.run("safety", "scan")


@nox.session
def doc(session: nox.Session) -> None:
    print("TODO: do something with the docs")


def run_subsession(session, sub_repo) -> None:
    name = session.name.split("(")[0]
    print(f"\nRunning session: {session.name} in subrepo: {sub_repo}\n")
    with session.chdir(sub_repo):
        session.run("nox", "-e", name, external=True)
    print()
