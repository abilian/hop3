# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The harness hands a check the same credentials the deploy does.

It did not. This runner read the encrypted credential store directly and wrote
``HOP3_ADMIN_*`` and nothing else, so ``Check.has_probe`` was false for every
app it tested: every check silently signed in as the operator's credential —
the weaker claim — while the deploy's own smoke test used the probe.

Piwigo turned weaker into wrong. On an empty gallery Piwigo answers an
onboarding interstitial to a guest or an administrator on every page, and to
an ordinary user it does not; the probe is an ordinary user. The 2026-09-14
catalog run logged both outcomes a minute apart, from the same check.py:
"Smoke test passed for 'piwigo-…'" from the deploy, and "check.py FAILED on
server" from here.

Which credentials a check gets is now the server's single decision
(`hop3.server.checks.runner.check_credentials`), asked for over the wire.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from hop3_testing.runners.deployment import DeploymentTestRunner

_READER_OUTPUT = (
    "HOP3_PROBE_USER=hop3probe\n"
    "HOP3_PROBE_EMAIL=probe@hop3.invalid\n"
    "HOP3_PROBE_PASSWORD=probe-pw\n"
    "HOP3_ADMIN_USER=admin\n"
    "HOP3_ADMIN_EMAIL=op@example.com\n"
    "HOP3_ADMIN_PASSWORD=admin-pw\n"
)


class _RecordingTarget:
    """Answers the credential reader; records every command it is given."""

    def __init__(self, reader_output: str = _READER_OUTPUT, exit_code: int = 0) -> None:
        self.reader_output = reader_output
        self.exit_code = exit_code
        self.commands: list[str] = []

    def exec_run(self, cmd: str) -> tuple[int, str, str]:
        self.commands.append(cmd)
        if "check_credentials" in cmd:
            return self.exit_code, self.reader_output, ""
        return 0, "", ""


def _write(target: _RecordingTarget) -> None:
    runner = DeploymentTestRunner(target=cast("Any", target), cleanup=True)
    session = SimpleNamespace(app_name="piwigo-1789384399")
    runner._write_check_credentials(cast("Any", session), "/tmp/piwigo.env")


def _env_file_body(target: _RecordingTarget) -> str:
    written = [c for c in target.commands if "HOP3EOF" in c]
    assert written, "no credential file was written"
    return written[0]


def test_the_probe_reaches_the_check():
    """The regression: these three lines were never written at all."""
    target = _RecordingTarget()
    _write(target)

    body = _env_file_body(target)
    assert "HOP3_PROBE_PASSWORD=probe-pw" in body
    assert "HOP3_PROBE_USER=hop3probe" in body
    assert "HOP3_PROBE_EMAIL=probe@hop3.invalid" in body


def test_the_admin_still_reaches_it_too():
    target = _RecordingTarget()
    _write(target)

    assert "HOP3_ADMIN_PASSWORD=admin-pw" in _env_file_body(target)


def test_the_server_decides_which_credentials():
    """
    Not this file. Re-deriving the rule here is how the two drifted: the
    server grew `HOP3_PROBE_CREATED` and nothing here knew.
    """
    target = _RecordingTarget()
    _write(target)

    reader = target.commands[0]
    assert "from hop3.server.checks.runner import check_credentials" in reader
    assert "AppAdminCredentialRepository" not in reader


def test_the_reader_survives_its_shell_quoting():
    """
    It travels inside `su - hop3 -c "… python -c \\"…\\""`, so a double quote
    anywhere in it ends the argument early and the reader runs as fragments.
    """
    target = _RecordingTarget()
    _write(target)

    reader = target.commands[0]
    python_snippet = reader.split('-c \\"', 1)[1].rsplit('\\"', 1)[0]
    assert '"' not in python_snippet
    compile(python_snippet, "<reader>", "exec")


def test_an_app_with_no_credentials_gets_an_empty_file():
    """
    The check's shell sources the file, and dash exits 2 on sourcing a missing
    one, before the check runs. No file for an app without `[admin]` failed
    every such check with "exit 2" and no output (2026-10-11, six fixtures).
    """
    target = _RecordingTarget(reader_output="")
    _write(target)

    body = _env_file_body(target)
    assert "HOP3_" not in body


def test_a_reader_that_could_not_run_fails_loudly():
    target = _RecordingTarget(reader_output="Traceback: no module", exit_code=1)

    with pytest.raises(RuntimeError, match="Traceback: no module"):
        _write(target)
    assert not [c for c in target.commands if "HOP3EOF" in c]
