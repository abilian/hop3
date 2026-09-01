# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
What the keys actually do.

The rest of the suite renders screens and asserts on the drawing. Nothing in it
presses a key, so every mutating operation — sixteen of them across six screens,
eight behind a `dialog.confirm` — was reachable only by reading the code. A
`confirm` wired backwards, acting on *cancel*, passed the whole suite.

These tests dispatch real key events and let the spawned coroutines finish, so an
assertion here is about what the app did, not about what it drew.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from hop3_tui.api.models import App, AppState, Backup, EnvVar
from hop3_tui.screens import Screen
from turbodesk.events import KeyPress

from .conftest import CANCEL, NO, YES, StubClient

APP = App(name="blog", state=AppState.RUNNING, runtime="python")
BACKUP = Backup(id="bk-1", app_name="blog", created_at=datetime(2026, 1, 1, tzinfo=UTC))
VAR = EnvVar(name="SECRET_KEY", value="s3cret")
#: The shape `Hop3Client.list_addons` actually returns — `app_name`, not `app`.
#: The screen used to read `app` for the table column, so an attached add-on
#: displayed as unattached while detach and delete correctly saw it as attached.
ADDON = {
    "name": "blogdb",
    "type": "postgresql",
    "app_name": "blog",
    "status": "running",
}
DETACHED = {"name": "spare", "type": "redis", "app_name": None, "status": "running"}
PROCESS = {"name": "blog", "pid": "42", "status": "running"}


# -- arriving on a screen fetches -----------------------------------------------------
#
# Regression: every screen used to register `ui.every` alone, which sleeps before its
# first call. Arriving on a screen showed an empty pane for a whole interval — ten
# seconds on apps, thirty on env vars — and the connection indicator sat on
# "Connecting..." for the same reason. Render-only tests could not see it: they assert
# on exactly the empty state the bug produced.


@pytest.mark.parametrize(
    ("screen", "call"),
    [
        (Screen.DASHBOARD, "list_apps"),
        (Screen.APPS, "list_apps"),
        (Screen.ADDONS, "list_addons"),
        (Screen.BACKUPS, "list_backups"),
        (Screen.ENV_VARS, "get_env_vars"),
        (Screen.PROCESSES, "get_processes"),
        (Screen.LOGS, "get_app_logs"),
        (Screen.SYSTEM_LOGS, "get_system_logs"),
    ],
)
def test_arriving_on_a_screen_fetches_at_once(drive, client, screen, call):
    drive(screen, argument="blog")

    assert client.called(call), f"{screen.value} drew itself without fetching anything"


def test_app_detail_fetches_the_app_and_its_logs(drive, client):
    client.returns["get_app"] = APP

    drive(Screen.APP_DETAIL, argument="blog")

    assert client.args_for("get_app") == ("blog",)
    assert client.called("get_app_logs")


# -- lifecycle: no confirmation, straight through --------------------------------------


@pytest.mark.parametrize(("key", "call"), [("s", "start_app"), ("r", "restart_app")])
def test_a_lifecycle_key_calls_the_client_for_the_selected_app(
    drive, client, key, call
):
    client.returns["list_apps"] = [APP]

    drive(Screen.APPS, [KeyPress(key)])

    assert client.args_for(call) == ("blog",)


def test_a_lifecycle_key_does_nothing_when_no_app_is_selected(drive, client):
    """An empty table must not send a call with a missing name."""
    client.returns["list_apps"] = []

    drive(Screen.APPS, [KeyPress("s")])

    assert not client.called("start_app")


def test_a_failed_lifecycle_call_is_reported_and_does_not_crash(drive, client):
    client.returns["list_apps"] = [APP]
    client.fails.add("start_app")

    text = drive(Screen.APPS, [KeyPress("s")])

    assert client.called("start_app")
    assert "start_app refused" in text


# -- the confirmation guard on every destructive operation -----------------------------
#
# Each case is asserted both ways round. Confirming must act; declining must not. A
# dialog wired to the wrong branch passes the first assertion alone.

DESTRUCTIVE = [
    pytest.param(Screen.APPS, "S", "stop_app", ("blog",), id="stop-app"),
    pytest.param(Screen.APPS, "D", "delete_app", ("blog",), id="delete-app"),
    pytest.param(Screen.BACKUPS, "d", "delete_backup", ("bk-1",), id="delete-backup"),
    pytest.param(Screen.BACKUPS, "r", "restore_backup", ("bk-1",), id="restore-backup"),
    pytest.param(
        Screen.ENV_VARS, "d", "delete_env_var", ("blog", "SECRET_KEY"), id="delete-var"
    ),
    pytest.param(Screen.ADDONS, "D", "delete_addon", ("spare",), id="delete-addon"),
]


def _seed(client: StubClient) -> None:
    client.returns.update(
        list_apps=[APP],
        list_backups=[BACKUP],
        get_env_vars=[VAR],
        list_addons=[DETACHED],
        get_processes=[PROCESS],
    )


@pytest.mark.parametrize(("screen", "key", "call", "args"), DESTRUCTIVE)
def test_confirming_a_destructive_action_performs_it(
    drive, client, screen, key, call, args
):
    _seed(client)

    drive(screen, [KeyPress(key), *YES], argument="blog")

    assert client.args_for(call) == args


@pytest.mark.parametrize(("screen", "key", "call", "args"), DESTRUCTIVE)
def test_declining_a_destructive_action_does_not_perform_it(
    drive, client, screen, key, call, args
):
    _seed(client)

    drive(screen, [KeyPress(key), *NO], argument="blog")

    assert not client.called(call), f"{call} ran after the dialog was declined"


@pytest.mark.parametrize(("screen", "key", "call", "args"), DESTRUCTIVE)
def test_escaping_a_destructive_action_does_not_perform_it(
    drive, client, screen, key, call, args
):
    """Escape dismisses the dialog, and dismissal is not consent."""
    _seed(client)

    drive(screen, [KeyPress(key), *CANCEL], argument="blog")

    assert not client.called(call)


def test_killing_a_process_asks_first(drive, client):
    _seed(client)

    drive(Screen.PROCESSES, [KeyPress("k"), *NO], argument="blog")

    assert not client.called("kill_process")


# -- detach and delete are different things (the audit found them conflated) -----------


def test_detach_unhooks_the_addon_without_deleting_it(drive, client):
    _seed(client)
    client.returns["list_addons"] = [ADDON]

    drive(Screen.ADDONS, [KeyPress("d")])

    assert client.args_for("detach_addon") == ("blogdb", "blog")
    assert not client.called("delete_addon")


def test_deleting_an_attached_addon_is_refused_before_it_is_asked(drive, client):
    """The server would refuse it; the screen must not even offer the dialog."""
    _seed(client)
    client.returns["list_addons"] = [ADDON]

    text = drive(Screen.ADDONS, [KeyPress("D"), *YES])

    assert not client.called("delete_addon")
    assert "Detach first" in text


def test_detaching_an_unattached_addon_says_so(drive, client):
    _seed(client)

    text = drive(Screen.ADDONS, [KeyPress("d")])

    assert not client.called("detach_addon")
    assert "not attached" in text


# -- refresh -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("screen", "call"),
    [
        (Screen.APPS, "list_apps"),
        (Screen.ADDONS, "list_addons"),
        (Screen.BACKUPS, "list_backups"),
        (Screen.ENV_VARS, "get_env_vars"),
    ],
)
def test_refresh_refetches(drive, client, screen, call):
    _seed(client)

    drive(screen, [KeyPress("R")], argument="blog")

    # Once on arrival, once for the key.
    assert sum(name == call for name, _ in client.calls) >= 2


# -- navigation ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "target"), [("l", Screen.LOGS), ("e", Screen.ENV_VARS)]
)
def test_a_navigation_key_pushes_the_screen_for_the_current_app(
    drive, client, key, target
):
    client.returns["get_app"] = APP
    pushed: list[tuple[Screen, str]] = []

    drive(Screen.APP_DETAIL, [KeyPress(key)], argument="blog", pushed=pushed)

    assert pushed == [(target, "blog")]


# -- the add-on table shows what the client actually returns ---------------------------


def test_the_addon_table_shows_the_app_an_addon_is_attached_to(drive, client):
    """`list_addons` returns `app_name`; the column used to read `app` and got "-"."""
    _seed(client)
    client.returns["list_addons"] = [ADDON]

    text = drive(Screen.ADDONS)

    assert "blogdb" in text
    assert "blog" in text.replace("blogdb", ""), "the APP column lost the app name"
