# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import nox

# Minimal version is 3.10
PYTHON_VERSIONS = ["3.10", "3.11", "3.12"]

nox.options.reuse_existing_virtualenvs = True

nox.options.reuse_existing_virtualenvs = True
# nox.options.default_venv_backend = "venv"

# Don't run 'update-deps' by default.
nox.options.sessions = [
    "lint",
    "pytest",
    "doc",
]

SUB_REPOS = [
    "hop3-agent",
    "hop3-server",
    "hop3-cli",
]


# @nox.session
# def lint(session: nox.Session) -> None:
#     session.install("--no-cache-dir", ".")
#     session.install("abilian-devtools")
#     session.run("make", "lint", external=True)
#
#
# @nox.session(python=PYTHON_VERSIONS)
# def pytest(session: nox.Session) -> None:
#     session.install("--no-cache-dir", ".")
#     session.install("pytest")
#     session.run("pytest", "--tb=short", "tests", external=True)


@nox.session(python=PYTHON_VERSIONS)
@nox.parametrize("sub_repo", SUB_REPOS)
def pytest(session: nox.Session, sub_repo: str) -> None:
    run_subsession(session, sub_repo)


@nox.session
@nox.parametrize("sub_repo", SUB_REPOS)
def lint(session: nox.Session, sub_repo: str) -> None:
    run_subsession(session, sub_repo)


@nox.session
def doc(session: nox.Session) -> None:
    print("TODO: do something with the docs")


@nox.session(name="update-deps")
def update_deps(session: nox.Session) -> None:
    for sub_repo in SUB_REPOS:
        with session.chdir(sub_repo):
            session.run("poetry", "install", external=True)
            session.run("poetry", "update", external=True)
        print()


def run_subsession(session, sub_repo) -> None:
    name = session.name.split("(")[0]
    print(f"\nRunning session: {session.name} in subrepo: {sub_repo}\n")
    with session.chdir(sub_repo):
        session.run("nox", "-e", name, external=True)
    print()
