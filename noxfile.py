# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import nox

# Minimal version is 3.10
# PYTHON_VERSIONS = ["3.10", "3.11", "3.12", "3.13", "3.14"]
# Actually, it's 3.11 for now
PYTHON_VERSIONS = ["3.11", "3.12", "3.13", "3.14"]

SUB_REPOS = [
    "packages/hop3-server",
    "packages/hop3-cli",
    "packages/hop3-testing",
]

# Note: we use 'uv' instead of 'pip' to make setup quicker
# '--active' and 'external=True' are needed for proper setup
nox.options.default_venv_backend = "uv|virtualenv"


nox.options.sessions = [
    "lint",
    "pytest",
]


@nox.session
def lint(session: nox.Session):
    """Run linters."""
    uv_sync(session)
    session.run("ruff", "check")
    session.run("reuse", "lint", "-q")

    # src_dirs = glob.glob("packages/*/src/") + glob.glob("packages/*/tests/")
    with session.chdir("packages/hop3-server"):
        session.run("deptry", "src")

    # session.run("vulture", "--min-confidence", "80", "packages/hop3-agent/src")


@nox.session(python=PYTHON_VERSIONS)
def pytest(session: nox.Session) -> None:
    uv_sync(session)
    session.run("pytest")


@nox.session(python=PYTHON_VERSIONS)
@nox.parametrize("sub_repo", SUB_REPOS)
def pytest_packages(session: nox.Session, sub_repo: str) -> None:
    run_subsession(session, sub_repo)


@nox.session
def audit(session: nox.Session) -> None:
    uv_sync(session)
    session.run("uv", "pip", "install", "--active", "safety", "pip-audit")
    session.run("pip-audit")
    session.run("safety", "scan")

    # session.run("uv", "pip", "install", ".")
    # session.run("uv", "pip", "install", "safety", "pip-audit")
    # session.run("pip-audit")
    # session.run("safety", "scan")


@nox.session
def doc(session: nox.Session) -> None:
    print("TODO: do something with the docs")


#
# Utils
#
def uv_sync(session: nox.Session):
    session.run("uv", "sync", "--active", external=True)
    # session.run("uv", "sync", "--all-groups", "--all-extras", "--active", external=True)


def run_subsession(session, sub_repo) -> None:
    name = session.name.split("(")[0]
    print(f"\nRunning session: {session.name} in subrepo: {sub_repo}\n")
    with session.chdir(sub_repo):
        session.run("nox", "-e", name, external=True)
    print()
