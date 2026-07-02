# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Deprecated `hop3-test` spellings still work but print a migration notice.

ADR 052 renamed the `system` subcommand to `run` (D9), `--deploy-from` to
`--from` (D3), and `--ssh-key` to `--identity` (D2). Each old spelling stays
accepted for one release and emits a one-line stderr notice. (The engine cannot
import hop3-installer's warn_deprecated, so it mirrors it locally.)
"""

from __future__ import annotations

import sys

from click.testing import CliRunner
from hop3_testing.cli import cli

# No target flag -> the command warns, then exits at the "must specify
# --docker or --ssh" check, before any deploy. So these run offline.


def test_system_subcommand_warns():
    result = CliRunner().invoke(cli, ["system"])
    assert "deprecated" in result.stderr
    assert "'system'" in result.stderr
    assert "'run'" in result.stderr


def test_deploy_from_flag_warns(monkeypatch):
    # The spelling is read from the real process argv (click can't tell which
    # alias of a shared option was typed), so drive the scan via sys.argv.
    monkeypatch.setattr(sys, "argv", ["hop3-test", "run", "--deploy-from", "git"])
    result = CliRunner().invoke(cli, ["run"])
    assert "'--deploy-from'" in result.stderr
    assert "'--from'" in result.stderr


def test_ssh_key_flag_warns(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["hop3-test", "run", "--ssh-key", "/k"])
    result = CliRunner().invoke(cli, ["run"])
    assert "'--ssh-key'" in result.stderr
    assert "'--identity'" in result.stderr


def test_canonical_run_is_silent(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["hop3-test", "run", "--from", "git"])
    result = CliRunner().invoke(cli, ["run"])
    assert "deprecated" not in result.stderr


def test_cloud_subcommand_warns():
    # `--list-images` just prints a constant list (no network) then returns.
    result = CliRunner().invoke(cli, ["cloud", "--list-images"])
    assert "deprecated" in result.stderr
    assert "'cloud'" in result.stderr
    assert "'matrix'" in result.stderr


def test_matrix_subcommand_is_silent():
    result = CliRunner().invoke(cli, ["matrix", "--list-images"])
    assert "deprecated" not in result.stderr
