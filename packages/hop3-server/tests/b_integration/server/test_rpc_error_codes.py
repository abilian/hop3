# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The JSON-RPC code says what kind of failure a command met.

`call()` wrapped every exception in a plain ValueError, so `_execute_command`
answered -32602 "Invalid params" for a full disk or a database error, and its
-32603 and RepositoryError branches never ran. Also covers the busy answer of
the one command slot, the protocol field, and the single identity resolution
per call.
"""

from __future__ import annotations

import threading
from typing import ClassVar

import pytest
from advanced_alchemy.exceptions import RepositoryError
from litestar.testing import TestClient

from hop3.commands import Command
from hop3.commands._errors import CommandFailedError
from hop3.config import HopConfig
from hop3.core.roles import Role
from hop3.lib.console import Abort
from hop3.orm import get_session_factory
from hop3.orm.session import reset_session_factory_cache
from hop3.server.asgi import create_app
from hop3.server.controllers import rpc as rpc_module
from hop3.server.controllers.rpc import (
    PROTOCOL_HEADER,
    RPC_ERROR_INTERNAL,
    RPC_ERROR_INVALID_PARAMS,
    RPC_ERROR_INVALID_REQUEST,
    RPC_ERROR_SERVER_BUSY,
    RPC_PROTOCOL_VERSION,
    ServerBusyError,
)


def _command(name: str, error: Exception) -> type[Command]:
    class Raising(Command):
        requires_auth: ClassVar[bool] = False
        min_role: ClassVar[Role] = Role.VIEWER

        def call(self, *args: str, **kwargs: object) -> list[dict]:
            raise error

    Raising.name = ("test-raise", name)
    return Raising


def _repository_error() -> RepositoryError:
    error = RepositoryError("There was an error during data processing")
    error.__cause__ = RuntimeError("UNIQUE constraint failed: app.name")
    return error


@pytest.fixture
def client(monkeypatch, worker_id, request):
    slug = f"{worker_id}_{abs(hash(request.node.nodeid)) % 10**8}"
    monkeypatch.setenv(
        "HOP3_DATABASE_URI",
        f"sqlite:///file:memdb_{slug}?mode=memory&cache=shared&uri=true",
    )
    reset_session_factory_cache()
    get_session_factory()
    monkeypatch.setattr(HopConfig, "HOP3_UNSAFE", property(lambda _self: True))
    for name, error in {
        "failed": CommandFailedError("disk full while writing the archive"),
        "repository": _repository_error(),
        "args": ValueError("Usage: hop3 test-raise args <name>"),
        "abort": Abort("deploy failed", explanation="npm ERR! code ENOSPC"),
    }.items():
        command = _command(name, error)
        monkeypatch.setitem(rpc_module._commands, command.name, command)
    yield TestClient(create_app())
    reset_session_factory_cache()


def _post(client, *cli_args: str, **params: object):
    return client.post(
        "/rpc/",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "cli",
            "params": {"cli_args": list(cli_args), "extra_args": {}, **params},
        },
    )


def test_a_failure_while_running_is_an_internal_error(client):
    error = _post(client, "test-raise", "failed").json()["error"]

    assert error["code"] == RPC_ERROR_INTERNAL
    assert error["message"] == "disk full while writing the archive"


def test_a_repository_error_keeps_its_diagnosis(client):
    error = _post(client, "test-raise", "repository").json()["error"]

    assert error["code"] == RPC_ERROR_INTERNAL
    assert "Database" in error["message"]
    assert "UNIQUE constraint failed: app.name" in error["message"]


def test_an_abort_reaches_the_client_with_its_explanation(client):
    """The explanation carries the hint and the failing command's output."""
    error = _post(client, "test-raise", "abort").json()["error"]

    assert error["code"] == RPC_ERROR_INTERNAL
    assert error["message"] == "deploy failed\nnpm ERR! code ENOSPC"


def test_a_bad_argument_stays_invalid_params(client):
    error = _post(client, "test-raise", "args").json()["error"]

    assert error["code"] == RPC_ERROR_INVALID_PARAMS
    assert error["message"] == "Usage: hop3 test-raise args <name>"


def test_every_response_reports_the_protocol(client):
    response = _post(client, "help")

    assert response.headers[PROTOCOL_HEADER] == str(RPC_PROTOCOL_VERSION)


def test_a_client_on_the_same_protocol_is_served(client):
    response = _post(client, "help", protocol=RPC_PROTOCOL_VERSION)

    assert "result" in response.json()


def test_a_client_on_another_protocol_is_refused_loudly(client):
    response = _post(client, "help", protocol=RPC_PROTOCOL_VERSION + 1)

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == RPC_ERROR_INVALID_REQUEST
    assert error["data"] == {
        "kind": "protocol_mismatch",
        "client_protocol": RPC_PROTOCOL_VERSION + 1,
        "server_protocol": RPC_PROTOCOL_VERSION,
    }
    assert response.headers[PROTOCOL_HEADER] == str(RPC_PROTOCOL_VERSION)


class _TakenSlot:
    """A command slot another command holds for the whole wait."""

    wait_seconds = 30.0

    holder = "backup create"

    def hold(self, display_name: str):
        raise ServerBusyError(self.holder, 95.4)


def test_a_call_that_cannot_get_the_slot_names_the_running_command(client, monkeypatch):
    monkeypatch.setattr(rpc_module, "_COMMAND_SLOT", _TakenSlot())

    response = _post(client, "help")

    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == RPC_ERROR_SERVER_BUSY
    assert "'hop3 backup create' has been running for 95s" in error["message"]
    assert error["data"] == {
        "kind": "server_busy",
        "running": "backup create",
        "running_for": 95,
    }


def test_the_identity_is_resolved_once_and_off_the_event_loop(
    file_db, account, monkeypatch
):
    monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key-for-rpc-error-codes")
    monkeypatch.setattr(HopConfig, "HOP3_UNSAFE", property(lambda _self: False))
    token = account("ana", Role.ADMIN)
    calls: list[int] = []
    real = rpc_module.current_identity

    def counting(request):
        calls.append(threading.get_ident())
        return real(request)

    monkeypatch.setattr(rpc_module, "current_identity", counting)
    client = TestClient(create_app())
    with client:
        loop_thread = client.blocking_portal.call(threading.get_ident)
        response = client.post(
            "/rpc/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "cli",
                # `auth whoami` passes the username, which read the token again.
                "params": {"cli_args": ["auth", "whoami"], "extra_args": {}},
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert "result" in response.json(), response.json()
    assert len(calls) == 1
    assert calls[0] != loop_thread


@pytest.mark.parametrize("protocol", [[1], {"v": 1}, True, "1"])
def test_a_malformed_protocol_is_a_json_rpc_error(client, protocol):
    """Unhashable values used to raise TypeError (an HTML 500); `true == 1`."""
    response = _post(client, "help", protocol=protocol)

    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["error"]["data"]["kind"] == "protocol_mismatch"
