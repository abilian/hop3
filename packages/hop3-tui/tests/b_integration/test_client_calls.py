# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
What each client method sends, and what it makes of the answer.

The TUI talks to the same JSON-RPC endpoint as `hop3-cli`: one `cli` method carrying
the CLI argv. Every typed method here is a thin wrapper that builds that argv, and
before these tests only the *read* methods had any coverage — a `delete_app` that
built `["app", "destroy", name]` would have gone to the server unnoticed.

The parsing half matters just as much: cells arrive as strings, and a screen that
formats a raw cell with `:.1f` raises on real data. That is a bug this file exists to
have caught.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from hop3_tui.api.client import Hop3Client, Hop3ClientError


@pytest.fixture
def sent() -> Any:
    """Call a client method against a stubbed transport; return the argv it sent.

    Yields a callable so a test reads as "do this, and this is what went out".
    """

    async def call(method: str, *args: Any, result: Any = None, **kwargs: Any):
        response = MagicMock(spec=httpx.Response)
        response.raise_for_status = MagicMock()
        response.json.return_value = {"jsonrpc": "2.0", "result": result, "id": 1}
        transport = AsyncMock(spec=httpx.AsyncClient)
        transport.post = AsyncMock(return_value=response)

        with patch("httpx.AsyncClient") as cls:
            cls.return_value.__aenter__ = AsyncMock(return_value=transport)
            cls.return_value.__aexit__ = AsyncMock(return_value=None)
            client = Hop3Client("http://hop3.test:8000")
            returned = await getattr(client, method)(*args, **kwargs)

        payload = transport.post.call_args.kwargs["json"]
        return payload["params"]["cli_args"], returned

    return call


# -- the argv every method builds ------------------------------------------------------
#
# Taken from hop3-cli, which is the reference client: `core/app_scope.py` for which
# commands are app-scoped and `main._inject_resolved_app` for where the flag goes —
# `--app NAME` right after the command name, never a positional (ADR 036 D5).

ARGV = [
    ("start_app", ("blog",), ["app", "start", "--app", "blog"]),
    ("stop_app", ("blog",), ["app", "stop", "--app", "blog"]),
    ("restart_app", ("blog",), ["app", "restart", "--app", "blog"]),
    ("delete_app", ("blog",), ["app", "destroy", "--app", "blog"]),
    (
        "create_app",
        ("blog", "g:/b.git"),
        ["app", "create", "g:/b.git", "--app", "blog"],
    ),
    ("deploy_app", ("blog",), ["deploy", "--app", "blog"]),
    ("set_env_var", ("blog", "K", "v"), ["env", "set", "--app", "blog", "K=v"]),
    ("delete_env_var", ("blog", "K"), ["env", "unset", "--app", "blog", "K"]),
    ("get_env_vars", ("blog",), ["env", "show", "--app", "blog"]),
    ("create_backup", ("blog",), ["backup", "create", "--app", "blog"]),
    ("delete_backup", ("bk-1",), ["backup", "destroy", "bk-1"]),
    ("restore_backup", ("bk-1",), ["backup", "restore", "bk-1"]),
    ("list_apps", (), ["app", "list"]),
    ("list_addons", (), ["addon", "list"]),
    ("create_addon", ("postgres", "db"), ["addon", "create", "postgres", "db"]),
    ("delete_addon", ("db",), ["addon", "destroy", "db"]),
    ("attach_addon", ("db", "blog"), ["addon", "attach", "db", "--app", "blog"]),
    ("detach_addon", ("db", "blog"), ["addon", "detach", "db", "--app", "blog"]),
    ("get_processes", ("blog",), ["ps", "--app", "blog"]),
    ("get_app", ("blog",), ["app", "status", "--app", "blog"]),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "args", "expected"), ARGV)
async def test_a_method_sends_the_command_it_names(sent, method, args, expected):
    argv, _ = await sent(method, *args)

    assert argv == expected


@pytest.mark.asyncio
async def test_a_transport_failure_becomes_a_client_error(sent):
    """Screens catch `Hop3ClientError`; anything else escapes and kills the frame."""
    transport = AsyncMock(spec=httpx.AsyncClient)
    transport.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
    with patch("httpx.AsyncClient") as cls:
        cls.return_value.__aenter__ = AsyncMock(return_value=transport)
        cls.return_value.__aexit__ = AsyncMock(return_value=None)
        with pytest.raises(Hop3ClientError, match="Request failed"):
            await Hop3Client("http://hop3.test:8000").list_apps()


# -- parsing the table the server sends back -------------------------------------------


def _table(*rows: list[str]) -> list[dict[str, Any]]:
    """A response carrying one table — a *list* of nodes, as the server sends.

    The caption and footnote around it are what `env show` adds, and what the
    client used to keep instead of the table.
    """
    return [{"t": "table", "headers": [], "rows": list(rows)}]


@pytest.mark.asyncio
async def test_ps_is_read_as_the_scaling_summary_the_server_sends(sent):
    """`ps` sends [Process Type, Count]. The client used to parse six columns."""
    _, processes = await sent(
        "get_processes", "blog", result=_table(["web", "3"], ["worker", "1"])
    )

    assert processes == [
        {"type": "web", "count": 3},
        {"type": "worker", "count": 1},
    ]


@pytest.mark.asyncio
async def test_an_unparseable_count_is_zero_rather_than_a_crash(sent):
    """Cells are strings; the screen used to format one with `:.1f` and raise."""
    _, processes = await sent("get_processes", "blog", result=_table(["web", "n/a"]))

    assert processes[0]["count"] == 0


@pytest.mark.asyncio
async def test_an_app_row_carries_its_instance_count_not_a_port(sent):
    """`app list` sends [Name, Status, Instances]; column three was read as a port."""
    _, apps = await sent("list_apps", result=_table(["blog", "RUNNING", "3"]))

    assert apps[0].workers == 3
    assert apps[0].port is None


@pytest.mark.asyncio
async def test_addons_carry_the_app_they_are_attached_to(sent):
    """The screen's APP column reads `app_name`; it once read `app` and got "-"."""
    _, addons = await sent(
        "list_addons", result=_table(["blogdb", "postgresql", "blog"])
    )

    assert addons[0]["app_name"] == "blog"


@pytest.mark.asyncio
async def test_an_unattached_addon_reads_as_unattached(sent):
    """`addon list` writes "-" in the third column when nothing is attached."""
    _, addons = await sent("list_addons", result=_table(["spare", "redis", "-"]))

    assert addons[0]["app_name"] is None


@pytest.mark.asyncio
async def test_a_missing_table_yields_nothing_rather_than_raising(sent):
    """A server that answers with text where a table was expected must not crash."""
    _, addons = await sent("list_addons", result=[{"t": "text", "text": "no addons"}])

    assert addons == []


@pytest.mark.asyncio
async def test_env_show_is_read_from_the_table_not_the_caption(sent):
    """The response is a *list*: a caption, the table, and a footnote.

    Keeping only the first node and reading it as a mapping is what the client did,
    so the environment screen listed `t` and `text` — the envelope's own keys — as
    an application's two variables, and never showed a real one.
    """
    _, variables = await sent(
        "get_env_vars",
        "blog",
        result=[
            {"t": "text", "text": "Configured environment for 'blog':"},
            {"t": "table", "headers": ["Key", "Value"], "rows": [["PORT", "8000"]]},
            {"t": "text", "text": "\nNote: These are configured values."},
        ],
    )

    assert [(v.name, v.value) for v in variables] == [("PORT", "8000")]


@pytest.mark.asyncio
async def test_revealing_secrets_is_a_flag_on_the_request(sent):
    """`env show` redacts before it answers, so revealing has to be a re-fetch."""
    argv, _ = await sent("get_env_vars", "blog", show_secrets=True)

    assert argv == ["env", "show", "--app", "blog", "--show-secrets"]


@pytest.mark.asyncio
async def test_app_status_fills_the_model_it_used_to_discard(sent):
    """`get_app` awaited the response and returned `App(name=name)` regardless."""
    _, app = await sent(
        "get_app",
        "blog",
        result=_table(
            ["Name", "blog"],
            ["Status", "RUNNING"],
            ["Instances", "3"],
            ["Local URL", "http://127.0.0.1:8123"],
            ["URL", "https://blog.example.com"],
        ),
    )

    assert app is not None
    assert (app.state.value, app.workers, app.port) == ("RUNNING", 3, 8123)
    assert app.hostname == "blog.example.com"


@pytest.mark.asyncio
async def test_a_crashed_app_is_a_state_the_client_can_name(sent):
    """`app status` reports CRASHED; `AppState(...)` raised out of the render."""
    _, app = await sent("get_app", "blog", result=_table(["Status", "CRASHED"]))

    assert app is not None
    assert app.state.value == "CRASHED"


@pytest.mark.asyncio
async def test_an_unknown_state_fails_loudly_rather_than_reading_as_stopped(sent):
    with pytest.raises(Hop3ClientError, match="unknown application state"):
        await sent("get_app", "blog", result=_table(["Status", "ASCENDED"]))


@pytest.mark.asyncio
async def test_backups_keep_the_size_the_server_formatted(sent):
    """`backup list` renders the size itself; the model read `size_bytes`, so
    every row showed a dash."""
    _, backups = await sent(
        "list_backups",
        result=_table(["bk-1", "blog", "5MB", "2026-03-15 12:00:00", "done", "pg"]),
    )

    assert (backups[0].id, backups[0].size) == ("bk-1", "5MB")
    assert backups[0].created == "2026-03-15 12:00:00"
