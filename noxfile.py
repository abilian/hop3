# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import glob

import nox

# Minimal version is 3.10
PYTHON_VERSIONS = ["3.10", "3.11", "3.12", "3.13"]

SUB_REPOS = [
    # "packages/hop3-agent",
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
def lint(session: nox.Session):
    """Run linters."""
    src_dirs = glob.glob("packages/*/src/") + glob.glob("packages/*/tests/")
    session.run("uv", "run", "--active", "ruff", "check", *src_dirs)
    # session.run("uv", "run", "pyright", "packages/hop3-server")
    # session.run("uv", "run", "mypy", "packages/hop3-server")
    session.run("uv", "run", "--active", "reuse", "lint", "-q")
    with session.chdir("packages/hop3-server"):
        session.run("uv", "run", "--active", "deptry", "src")

    # session.run("vulture", "--min-confidence", "80", "packages/hop3-agent/src")


@nox.session(python=PYTHON_VERSIONS)
def pytest(session: nox.Session) -> None:
    # session.install(".")
    # session.install("pytest")
    session.run("uv", "run", "pytest")


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
