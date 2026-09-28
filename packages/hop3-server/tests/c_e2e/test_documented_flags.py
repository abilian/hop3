# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
E2E: the flags a command documents reach it through the real `hop3` binary.

The client parses argv before the server sees it, and it used to keep flags
the commands needed: it refused `--app` for `addon list`, swallowed
`--dry-run` and `--quiet`, and a command missing its argument printed the
usage with exit 0. Each test here asserts the server's own answer, which only
arrives if the client passed the flag on.
"""

from __future__ import annotations

import re
import subprocess
from typing import Any

import pytest
from hop3_testing.targets.constants import hermetic_cli_cwd

from .conftest import cli_env

USAGE_ERROR = 2


def _hop3(container: dict[str, Any], *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["hop3", *args],
        env=cli_env(container),
        cwd=hermetic_cli_cwd(),
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.e2e
def test_addon_list_takes_app_as_a_filter(hop3_container: dict[str, Any]):
    result = _hop3(hop3_container, "addon", "list", "--app", "no-such-app")
    output = result.stdout + result.stderr
    assert "does not take --app" not in output, output
    assert "App 'no-such-app' not found" in output, output


@pytest.mark.e2e
def test_a_missing_argument_is_a_usage_error(hop3_container: dict[str, Any]):
    """`export > dump.sql` with no name wrote the usage into the dump, exit 0."""
    result = _hop3(hop3_container, "addon", "postgres", "export")
    assert result.returncode == USAGE_ERROR, result.stdout + result.stderr
    assert result.stdout == ""
    assert "Usage: hop3 addon postgres export <name>" in result.stderr


@pytest.mark.e2e
def test_dry_run_reaches_the_command(hop3_container: dict[str, Any]):
    result = _hop3(hop3_container, "admin", "reencrypt-credentials", "--dry-run")
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "Would re-encrypt" in output, output


@pytest.mark.e2e
def test_quiet_status_is_one_line(hop3_container: dict[str, Any]):
    result = _hop3(hop3_container, "system", "status", "--quiet")
    lines = [line for line in (result.stdout + result.stderr).splitlines() if line]
    assert len(lines) == 1, lines
    assert re.search(r"\b(OK|DEGRADED|FAILED)\b", lines[0]), lines


@pytest.mark.e2e
def test_nix_eject_runs_instead_of_printing_help(hop3_container: dict[str, Any]):
    result = _hop3(hop3_container, "nix", "eject", "--app", "no-such-app")
    output = result.stdout + result.stderr
    assert "SUBCOMMANDS" not in output, output
    assert "no-such-app" in output, output
    assert "not found" in output, output
