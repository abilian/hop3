# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Only a refused credential is an authentication failure.

A destroy sent while the server was still busy with an upgrade timed out on its
pre-confirmation `auth whoami`, and the CLI said "No credential for ...", exit 4,
and advised logging in again.
"""

from __future__ import annotations

from typing import Self

import pytest
import requests
from hop3_cli import main
from hop3_cli.exceptions import AuthenticationError
from hop3_cli.exit_codes import RPC_UNAUTHENTICATED, ExitCode
from jsonrpcclient import Error, Ok


class _Client:
    """Answers `auth whoami` with the response, or raises it."""

    response: object = None
    rpc_url = "http://localhost:8000/rpc"
    api_url = rpc_url
    tunnel = None

    def __init__(self, **_kw) -> None:
        pass

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc) -> None:
        pass

    def rpc(self, *_args):
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.fixture
def answer(monkeypatch):
    def set_answer(response) -> None:
        monkeypatch.setattr(_Client, "response", response)

    monkeypatch.setattr(main, "Client", _Client)
    return set_answer


def test_a_server_too_slow_to_answer_is_a_network_error(answer, capsys):
    answer(requests.exceptions.ReadTimeout("Read timed out. (read timeout=300.0)"))

    with pytest.raises(SystemExit) as exit_:
        main.verify_authentication(config=None)

    assert exit_.value.code == ExitCode.NETWORK_ERROR
    assert "did not answer in time" in capsys.readouterr().err


def test_a_server_error_is_reported_as_itself(answer, capsys):
    answer(Error(-32603, "database is locked", "", 1))

    with pytest.raises(SystemExit) as exit_:
        main.verify_authentication(config=None)

    assert exit_.value.code == ExitCode.NETWORK_ERROR
    assert "database is locked" in capsys.readouterr().err


def test_a_refused_credential_is_an_authentication_error(answer):
    answer(Error(RPC_UNAUTHENTICATED, "Token expired", "", 1))

    with pytest.raises(AuthenticationError, match="Token expired"):
        main.verify_authentication(config=None)


def test_an_older_server_refusing_in_prose_is_one_too(answer):
    answer(Error(-32000, "Authentication required", "", 1))

    with pytest.raises(AuthenticationError):
        main.verify_authentication(config=None)


def test_an_accepted_credential_passes(answer):
    answer(Ok({"user": "admin"}, 1))

    main.verify_authentication(config=None)
