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

import pytest
from click.testing import CliRunner
from hop3_testing.cli import cli


@pytest.fixture(autouse=True)
def _no_ambient_target(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep these tests offline.

    With no target flag they must exit at the "specify --docker or --host"
    check, before any deploy. --host resolves from $HOP3_HOST (ADR 052 D2), so a
    leaked value would select the remote target and fall through to a real
    deploy — clear it. (HOP3_TEST_HOST / HOP3_DEV_HOST are retired (ADR 043) and
    already stripped session-wide by the root conftest, so they need no clear.)
    """
    monkeypatch.delenv("HOP3_HOST", raising=False)


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


def test_ssh_mode_flag_warns(monkeypatch):
    # ADR 052 D2: --ssh is a deprecated alias; --host implies the remote target.
    monkeypatch.setattr(sys, "argv", ["hop3-test", "run", "--ssh"])
    result = CliRunner().invoke(cli, ["run"])
    assert "'--ssh'" in result.stderr
    assert "'--host'" in result.stderr


def test_canonical_run_is_silent(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["hop3-test", "run", "--from", "git"])
    result = CliRunner().invoke(cli, ["run"])
    assert "deprecated" not in result.stderr


def test_matrix_and_cloud_commands_are_gone():
    # Folded into `run --images` (ADR 052 D9); neither is a subcommand anymore.
    for gone in ("matrix", "cloud"):
        result = CliRunner().invoke(cli, [gone, "--list-images"])
        assert result.exit_code != 0
        assert (
            "No such command" in result.output
            or "no such command" in result.output.lower()
        )
