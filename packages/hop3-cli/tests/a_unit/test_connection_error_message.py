# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""A transport failure must report the cause it had, not a guessed one."""

from __future__ import annotations

import pytest
import requests
from hop3_cli.main import _handle_connection_error

URL = "http://localhost:53669/rpc"


def _report(exc: Exception, capsys) -> str:
    with pytest.raises(SystemExit):
        _handle_connection_error(exc, URL)
    return capsys.readouterr().err


def test_mid_upload_timeout_does_not_claim_the_server_is_down(capsys) -> None:
    exc = requests.exceptions.ConnectionError((
        "Connection aborted.",
        TimeoutError("timed out"),
    ))
    out = _report(exc, capsys)
    assert "timed out" in out  # the actual cause, not swallowed
    assert "Is it running?" not in out  # a cause we did not observe


def test_refused_connection_still_suggests_the_server_is_down(capsys) -> None:
    exc = requests.exceptions.ConnectionError("[Errno 61] Connection refused")
    out = _report(exc, capsys)
    assert "Is it running?" in out
