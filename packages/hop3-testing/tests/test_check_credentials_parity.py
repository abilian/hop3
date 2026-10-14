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

import json
import subprocess
import sys
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
from hop3_testing.runners.deployment import DeploymentTestRunner

if TYPE_CHECKING:
    from pathlib import Path

_CREDENTIALS = {
    "HOP3_PROBE_USER": "hop3probe",
    "HOP3_PROBE_EMAIL": "probe@hop3.invalid",
    "HOP3_PROBE_PASSWORD": "probe-pw",
    "HOP3_ADMIN_USER": "admin",
    "HOP3_ADMIN_EMAIL": "op@example.com",
    "HOP3_ADMIN_PASSWORD": "admin-pw",
}
_ENV_PATH = "/tmp/piwigo.env"


class _RecordingTarget:
    """Records every command; the reader's command exits as told."""

    def __init__(self, exit_code: int = 0, stderr: str = "") -> None:
        self.exit_code = exit_code
        self.stderr = stderr
        self.commands: list[str] = []

    def exec_run(self, cmd: str) -> tuple[int, str, str]:
        self.commands.append(cmd)
        if "check_credentials" in cmd:
            return self.exit_code, "", self.stderr
        return 0, "", ""


def _write(target: _RecordingTarget) -> None:
    runner = DeploymentTestRunner(target=cast("Any", target), cleanup=True)
    session = SimpleNamespace(app_name="piwigo-1789384399")
    runner._write_check_credentials(cast("Any", session), _ENV_PATH)


def _reader_command() -> str:
    target = _RecordingTarget()
    _write(target)
    (command,) = target.commands
    return command


def _python_snippet(command: str) -> str:
    return command.split('-c \\"', 1)[1].rsplit('\\"', 1)[0]


#: Stand-ins for the server's modules, which the reader imports. Put first on
#: PYTHONPATH, they take precedence over anything installed.
_STUBS = {
    "sqlalchemy/__init__.py": (
        "class _Statement:\n"
        "    def where(self, _condition):\n"
        "        return self\n"
        "def select(_model):\n"
        "    return _Statement()\n"
    ),
    "hop3/__init__.py": "",
    "hop3/orm.py": (
        "import os\n"
        "class App:\n"
        "    name = 'name'\n"
        "class _Result:\n"
        "    def one_or_none(self):\n"
        "        return App() if os.environ['STUB_CREDENTIALS'] != 'null' else None\n"
        "class _Session:\n"
        "    def scalars(self, _statement):\n"
        "        return _Result()\n"
        "def get_session_factory():\n"
        "    return _Session\n"
    ),
    "hop3/server/__init__.py": "",
    "hop3/server/checks/__init__.py": "",
    "hop3/server/checks/runner.py": (
        "import json, os\n"
        "def check_credentials(_app, _session):\n"
        "    return json.loads(os.environ['STUB_CREDENTIALS'])\n"
    ),
}


def _run_reader(tmp_path: Path, credentials: dict[str, str] | None) -> str:
    """
    Run the reader the server would run, against stand-ins for the server's
    modules, and return what it writes into the file.
    """
    stubs = tmp_path / "stubs"
    for relative, source in _STUBS.items():
        path = stubs / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    result = subprocess.run(
        [sys.executable, "-c", _python_snippet(_reader_command())],
        capture_output=True,
        text=True,
        check=True,
        env={
            "PYTHONPATH": str(stubs),
            "STUB_CREDENTIALS": json.dumps(credentials),
        },
    )
    return result.stdout


def _sourced(tmp_path: Path, body: str, key: str) -> str:
    """What a shell that sources ``body`` sees in ``key``."""
    env_file = tmp_path / "check.env"
    env_file.write_text(body)
    result = subprocess.run(
        ["sh", "-c", f'set -a; . "$1"; printf %s "${key}"', "sh", str(env_file)],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_the_probe_reaches_the_check(tmp_path):
    """The regression: these three lines were never written at all."""
    body = _run_reader(tmp_path, _CREDENTIALS)

    assert _sourced(tmp_path, body, "HOP3_PROBE_PASSWORD") == "probe-pw"
    assert _sourced(tmp_path, body, "HOP3_PROBE_USER") == "hop3probe"
    assert _sourced(tmp_path, body, "HOP3_PROBE_EMAIL") == "probe@hop3.invalid"


def test_the_admin_still_reaches_it_too(tmp_path):
    body = _run_reader(tmp_path, _CREDENTIALS)

    assert _sourced(tmp_path, body, "HOP3_ADMIN_PASSWORD") == "admin-pw"


def test_a_password_the_shell_would_expand_arrives_intact(tmp_path):
    """The file is sourced: unquoted, `$`, a space or a quote would change it."""
    password = "a b$HOME'\"`x`;"
    body = _run_reader(tmp_path, {"HOP3_ADMIN_PASSWORD": password})

    assert _sourced(tmp_path, body, "HOP3_ADMIN_PASSWORD") == password


def test_the_credentials_never_appear_on_a_command_line():
    """
    The reader writes the file on the server. Sending its output back to be
    written by a second command put every secret in that command's argv.
    """
    command = _reader_command()

    assert command.endswith(f'> {_ENV_PATH}"')
    assert "umask 077" in command
    assert "probe-pw" not in command


def test_the_server_decides_which_credentials():
    """
    Not this file. Re-deriving the rule here is how the two drifted: the
    server grew `HOP3_PROBE_CREATED` and nothing here knew.
    """
    reader = _reader_command()

    assert "from hop3.server.checks.runner import check_credentials" in reader
    assert "AppAdminCredentialRepository" not in reader


def test_the_reader_survives_its_shell_quoting():
    """
    It travels inside `su - hop3 -c "… python -c \\"…\\""`, so a double quote,
    a `$` or a backquote anywhere in it is taken by the outer shell.
    """
    python_snippet = _python_snippet(_reader_command())

    assert not set('"$`') & set(python_snippet)
    compile(python_snippet, "<reader>", "exec")


def test_an_app_with_no_credentials_gets_an_empty_file(tmp_path):
    """
    The check's shell sources the file, and dash exits 2 on sourcing a missing
    one, before the check runs. No file for an app without `[admin]` failed
    every such check with "exit 2" and no output (2026-10-11, six fixtures).
    """
    assert _run_reader(tmp_path, None) == ""
    assert _reader_command().endswith(f'> {_ENV_PATH}"')


def test_a_reader_that_could_not_run_fails_loudly():
    target = _RecordingTarget(exit_code=1, stderr="Traceback: no module")

    with pytest.raises(RuntimeError, match="Traceback: no module"):
        _write(target)
