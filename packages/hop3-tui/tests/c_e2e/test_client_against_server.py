# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Every client method, against a running server.

This is the layer that was missing. The client's argv had drifted on three axes —
command names (`apps` for `app list`, `addons` for `addon`), the app target (a
positional where ADR 036 D5 requires `--app NAME`), and the shape of what came back
(`app list`'s third column read as a port when it is the instance count) — and none
of it was visible to a suite that stubbed the transport and asserted on responses
the tests themselves invented.

A static contract test now pins the first two axes against the server's source. Only
this layer pins the third, because only a real server sends a real table.

The read methods run against an empty server: what is asserted is that the call is
*accepted and parses*, which is exactly what was broken. An unknown command comes
back as a `Hop3ClientError` naming it, so a regression here is loud and specific.
"""

from __future__ import annotations

import pytest
from hop3_tui.api.client import Hop3Client, Hop3ClientError
from hop3_tui.api.models import App, Backup, EnvVar

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# -- the read methods every screen opens with ------------------------------------------
#
# Each is what a screen calls on arrival. Before the rewrite, six of these raised
# because the server had never heard of the command.


async def test_list_apps_parses_the_real_table(api: Hop3Client, deployed_app: str):
    """`app list` sends [Name, Status, Instances].

    Needs a deployed app: an empty server answers `{"t": "text"}`, so no row is
    parsed and this assertion passes without testing anything. That is how the
    instance-count-read-as-a-port bug survived this layer's first run.
    """
    apps = await api.list_apps()

    assert deployed_app in [app.name for app in apps]
    app = next(a for a in apps if a.name == deployed_app)
    assert isinstance(app, App)
    # Column three is the instance count. It was read as a port for years, and the
    # server sends it as an int here and a str elsewhere — both must parse.
    assert app.workers >= 1
    assert app.port is None, "the server sends no port in `app list`"


async def test_list_addons_is_accepted_and_parses(api: Hop3Client):
    """Sent `addons list` for years; the server's namespace is `addon`."""
    addons = await api.list_addons()

    assert isinstance(addons, list)
    for addon in addons:
        # The keys the addons screen reads. `app_name` is the one the table column
        # used to miss, showing "-" for every attached add-on.
        assert set(addon) == {"name", "type", "app_name"}


async def test_list_backups_is_accepted_and_parses(api: Hop3Client):
    backups = await api.list_backups()

    assert isinstance(backups, list)
    assert all(isinstance(backup, Backup) for backup in backups)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Not a TUI bug and not command drift — the server dispatches `system "
        "status` fine, then it fails inside: `_check_services` shells out to "
        "`systemctl is-active` unconditionally, and the e2e container is "
        "supervisor-managed, so there is no systemctl. Service checks have to be "
        "process-manager-aware the way the deployer's `service_restart_command` "
        "already is. Reported, not fixed here; this turns green on its own."
    ),
)
async def test_get_system_status_is_accepted(api: Hop3Client):
    """Still a stub client-side, but the call must reach a real command."""
    await api.get_system_status()


async def test_get_system_info_is_accepted_and_parses(api: Hop3Client):
    info = await api.get_system_info()

    assert isinstance(info, dict)


async def test_get_system_logs_is_accepted_and_parses(api: Hop3Client):
    lines = await api.get_system_logs(lines=5)

    assert isinstance(lines, list)
    assert all(isinstance(line, str) for line in lines)


# -- the app-scoped methods, whose target used to be a positional ----------------------
#
# The server takes the app from `--app` only and calls `reject_extra_args` on what is
# left, so a positional name did not merely miss — it failed loudly. These assert the
# call is understood: an unknown app is a normal answer, an unknown *command* or a
# rejected stray token is not.

APP_SCOPED_READS = ["get_app", "get_app_logs", "get_env_vars", "get_processes"]


@pytest.mark.parametrize("method", APP_SCOPED_READS)
async def test_an_app_scoped_read_is_understood(api: Hop3Client, method: str):
    """An unknown app is a normal answer. Anything else means we were not understood.

    Asserted as an allowlist, not a list of error phrases to avoid: the first version
    of this test guessed at "unexpected" / "usage:" and missed the real wording,
    "Unrecognized argument(s): 'no-such-app'" — so a positional app name sailed
    through the very check written to catch it.
    """
    message = ""
    try:
        await getattr(api, method)("no-such-app")
    except Hop3ClientError as error:
        message = str(error).lower()

    assert not message or "not found" in message, (
        f"{method} was not understood by the server: {message}"
    )


@pytest.mark.parametrize("method", APP_SCOPED_READS)
async def test_an_app_scoped_read_works_on_a_real_app(
    api: Hop3Client, deployed_app: str, method: str
):
    """The same calls against an app that exists, so the answers actually parse."""
    await getattr(api, method)(deployed_app)


async def test_env_vars_parse_into_the_model(api: Hop3Client, deployed_app: str):
    """`env show` is the command; the client sent `config show` until recently.

    `config` is a real server-side alias, so this one never broke — which is why the
    static check had to learn to read `aliases:` before it stopped crying wolf.
    """
    variables = await api.get_env_vars(deployed_app)

    assert all(isinstance(v, EnvVar) for v in variables)


async def test_processes_parse_as_the_scaling_summary(
    api: Hop3Client, deployed_app: str
):
    """`ps` sends [Process Type, Count]; the client used to parse six columns."""
    processes = await api.get_processes(deployed_app)

    assert processes, "a deployed app has at least one process type"
    for process in processes:
        assert set(process) == {"type", "count"}
        assert isinstance(process["count"], int)
    assert "web" in [p["type"] for p in processes]


# -- the guard rail --------------------------------------------------------------------


async def test_an_unknown_command_really_does_fail(api: Hop3Client):
    """Proves the tests above are not passing because everything succeeds.

    Without this, a server that answered anything with a cheerful empty result would
    make every assertion here vacuous.
    """
    with pytest.raises(Hop3ClientError):
        await api._rpc_call(["definitely-not-a-command"])


async def test_the_server_is_the_one_we_think(api: Hop3Client):
    """A smoke check that authentication works, so failures above mean what they say."""
    apps = await api.list_apps()

    assert isinstance(apps, list)
