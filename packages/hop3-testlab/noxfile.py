"""Nox configuration."""

from __future__ import annotations

import nox

PYTHONS = ["3.10", "3.11", "3.12", "3.13", "3.14"]


@nox.session(python=PYTHONS)
def tests(session: nox.Session):
    """Run the test suite."""
    uv_sync(session)
    session.run("pytest")
    # Or:
    # session.run("uv", "run", "--active", "make", "test")


@nox.session
def check(session: nox.Session):
    """Run all checks (lint, typecheck, tests)."""
    uv_sync(session)
    session.run("ruff", "check")
    session.run("ruff", "format", "--check")
    session.run("ty", "check", "src")
    # session.run("pyrefly", "check", "src")
    # session.run("mypy", "src")
    # session.run("mypy", "--strict", "src")
    # Or:
    # session.run("uv", "run", "--active", "make", "check")


#
# Utils
#
def uv_sync(session: nox.Session):
    session.run("uv", "sync", "-q", "--active", external=True)
    # session.run("uv", "sync", "-q", "--all-groups", "--all-extras", "--active", external=True)
