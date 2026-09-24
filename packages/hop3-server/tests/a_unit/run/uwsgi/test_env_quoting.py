# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Env values survive the trip through the worker's env file.

An ``attach-daemon`` worker gets its environment by sourcing a file of
``export`` lines, so every value must come back from a real ``/bin/sh``
byte-identical. The values below broke an earlier encoding: a JSON-valued
setting arrived with its quotes stripped (paperless-ngx's
PAPERLESS_PROXY_SSL_HEADER reached Django as ``[HTTP_X_FORWARDED_PROTO,https]``
and crashed every worker), and a generated password containing ``$`` would have
been silently mangled into a credential that no longer opened the account.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from hop3.run.uwsgi.worker import GenericWorker

if TYPE_CHECKING:
    from pathlib import Path

ROUND_TRIP_CASES = [
    pytest.param("plain-value-123", id="plain"),
    pytest.param('["HTTP_X_FORWARDED_PROTO","https"]', id="json-list"),
    pytest.param("it's a password", id="apostrophe"),
    pytest.param('a$b"c`d\\e', id="every-metacharacter"),
    pytest.param("postgresql://u:p$w`x'y@h:5432/db", id="database-url"),
    pytest.param("$PORT", id="literal-dollar-name"),
    pytest.param("line one\nline two", id="newline"),
]


def _source_and_read_back(value: str, tmp_path: Path) -> str:
    """Source the file ``attach_daemon`` writes, the way the daemon's shell does."""
    worker = GenericWorker("quoting", "true", {"V": value}, kind="worker")
    worker.update_settings()
    env_file = tmp_path / "worker.env"
    env_file.write_text(worker.env_file_text)
    result = subprocess.run(
        ["/bin/sh", "-c", f'. "{env_file}" && printenv V'],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.removesuffix("\n")


@pytest.mark.parametrize("value", ROUND_TRIP_CASES)
def test_env_value_survives_the_env_file(value: str, tmp_path: Path) -> None:
    assert _source_and_read_back(value, tmp_path) == value
