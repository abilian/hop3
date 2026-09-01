# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""The screens.

The original drove each screen through `app.run_test()` and asserted on the widget tree
(`query_one(DataTable).columns`). A screen here is a function returning a `View`, so the
pure parts are tested directly and the rendering is checked by what comes out.
"""

from __future__ import annotations

import pytest
from hop3_tui.api.models import App as AppModel, AppState, Backup as BackupModel
from hop3_tui.app import Hop3TUI
from hop3_tui.config import TUIConfig
from hop3_tui.screens import (
    SCREENS,
    Screen,
    apps as apps_screen,
    backups as backups_screen,
    chat as chat_screen,
    env_vars as env_screen,
)
from hop3_tui.screens._common import halves
from hop3_tui.screens._logview import line_role
from turbodesk import UI, Size
from turbodesk.testing import render, to_text
from turbodesk.theme import MOCHA

SIZE = Size(78, 16)


@pytest.fixture
def hop3() -> Hop3TUI:
    return Hop3TUI(TUIConfig(server_url="http://localhost:1"))


@pytest.fixture
def draw(hop3: Hop3TUI):
    """Render one screen on its own, the way the app does — inside its own scope."""

    def one(screen: Screen, argument: str = "", size: Size = SIZE) -> str:
        def wrapper(ui):
            with ui.scope(screen):
                return SCREENS[screen](
                    ui,
                    hop3,
                    size,
                    argument=argument,
                    push=lambda *_: None,
                    switch=lambda _: None,
                )

        return to_text(render(wrapper, size=size))

    return one


def app_model(name: str = "blog", state: AppState = AppState.RUNNING) -> AppModel:
    return AppModel(name=name, state=state, runtime="python", port=8000)


# -- every screen renders -------------------------------------------------------------


@pytest.mark.parametrize("screen", list(Screen))
def test_every_screen_renders_without_error(draw, screen: Screen):
    assert draw(screen, "blog")


@pytest.mark.parametrize("screen", list(Screen))
def test_no_screen_is_blank(draw, screen: Screen):
    assert draw(screen, "blog").strip(), "a blank screen reads as a layout bug"


@pytest.mark.parametrize("size", [Size(40, 10), Size(120, 40), Size(78, 16)])
def test_screens_render_at_any_size(draw, size: Size):
    assert draw(Screen.DASHBOARD, size=size)


# -- dashboard ------------------------------------------------------------------------


def test_the_dashboard_shows_its_four_panels(draw):
    text = draw(Screen.DASHBOARD)

    for title in ("APPLICATIONS", "SYSTEM STATUS", "RECENT ACTIVITY", "ACTIONS"):
        assert title in text


def test_the_dashboard_counts_start_at_zero(draw):
    assert "Running: 0" in draw(Screen.DASHBOARD)


# The `[b]`-is-not-bold guard moved to tests/a_unit/test_widgets.py: it was asserted
# through the dashboard's "[b] Create backup" literal, and that literal is gone —
# it advertised a key the screen never bound. The invariant is about the markup
# parser, so it is now tested against the parser.


# -- system ---------------------------------------------------------------------------


def test_the_system_screen_shows_its_panels(draw):
    text = draw(Screen.SYSTEM)

    assert "RESOURCES" in text
    assert "SERVICES" in text
    assert "INFO" in text


def test_the_system_screen_invents_no_services(draw):
    """It used to render four services as RUNNING whatever the server said."""
    text = draw(Screen.SYSTEM)

    assert "nginx" not in text
    assert "RUNNING" not in text
    assert "not reported by the server" in text


def test_the_resources_panel_draws_no_gauge_without_a_measurement(draw):
    """The bar used to be drawn from three constants, so it was always full."""
    text = draw(Screen.SYSTEM)

    assert "█" not in text
    for constant in ("42%", "63%", "81%"):
        assert constant not in text


# -- apps: filtering and rows ---------------------------------------------------------


def test_filtering_keeps_only_matching_names():
    apps = [app_model("blog"), app_model("shop"), app_model("blogroll")]

    assert [a.name for a in apps_screen.matching(apps, "blog")] == ["blog", "blogroll"]


def test_filtering_ignores_case():
    assert apps_screen.matching([app_model("Blog")], "blog")


def test_an_empty_filter_keeps_everything():
    apps = [app_model("blog"), app_model("shop")]

    assert apps_screen.matching(apps, "") == apps


def test_the_apps_table_has_its_columns(draw):
    text = draw(Screen.APPS)

    # Only what `app list` returns. PORT, RUNTIME and UPDATED were columns the
    # server never fills — PORT showed the instance count, the others a dash.
    for heading in ("NAME", "STATUS", "INSTANCES"):
        assert heading in text
    for absent in ("PORT", "RUNTIME", "UPDATED"):
        assert absent not in text


def test_a_row_carries_the_apps_fields():
    ui = UI(SIZE, MOCHA)

    name, status, instances = apps_screen.table_rows(ui, [app_model("blog")])[0]

    assert name == "blog"
    assert status.text == "RUNNING"
    assert instances == "1"


def test_the_instance_count_is_the_one_the_server_sent():
    """It is the third column of `app list`, and was once read as a port."""
    ui = UI(SIZE, MOCHA)
    app = AppModel(name="blog", state=AppState.RUNNING, workers=3)

    assert apps_screen.table_rows(ui, [app])[0][2] == "3"


@pytest.mark.parametrize(
    "state", [AppState.RUNNING, AppState.STOPPED, AppState.FAILED, AppState.STARTING]
)
def test_each_state_gets_its_own_colour(state: AppState):
    ui = UI(SIZE, MOCHA)

    cell = apps_screen.table_rows(ui, [app_model("blog", state)])[0][1]

    assert cell.style is not None, "the badge colour is what the CSS classes encoded"


def test_the_apps_screen_says_when_there_is_nothing(draw):
    assert "(no apps)" in draw(Screen.APPS)


# -- env vars -------------------------------------------------------------------------


def test_a_long_value_is_elided():
    formatted = env_screen.format_value("x" * 100)

    assert formatted.endswith("...")
    assert len(formatted) == env_screen.MAX_VALUE


def test_a_short_value_is_left_alone():
    assert env_screen.format_value("production") == "production"


def test_the_env_vars_table_has_its_columns(draw):
    text = draw(Screen.ENV_VARS, "blog")

    for heading in ("NAME", "VALUE"):
        assert heading in text
    # The TYPE column reported "secret"/"plain" from a heuristic run over an
    # already-redacted value. It was wrong in both directions.
    assert "TYPE" not in text


# -- backups --------------------------------------------------------------------------


def test_a_backup_row_shows_the_size_the_server_rendered():
    """`backup list` formats the size; the screen read a `size_bytes` field that
    the wire never carries, so every row's size column was a dash."""
    backup = BackupModel(id="bk-1", app_name="blog", size="5MB", created="today")

    assert backups_screen.table_rows([backup])[0][2] == "5MB"


def test_the_backups_table_has_its_columns(draw):
    text = draw(Screen.BACKUPS)

    for heading in ("ID", "APP", "SIZE", "CREATED", "ADDONS"):
        assert heading in text


# -- addons and processes -------------------------------------------------------------


def test_the_addons_table_has_its_columns(draw):
    text = draw(Screen.ADDONS)

    # `addon list` sends [Name, Type, Attached apps]; there is no status column.
    for heading in ("NAME", "TYPE", "ATTACHED TO"):
        assert heading in text
    assert "STATUS" not in text


def test_the_processes_table_has_its_columns(draw):
    text = draw(Screen.PROCESSES, "blog")

    # `ps` answers "how many workers of each type", in two columns. The five it
    # used to advertise have no server-side data at all.
    for heading in ("PROCESS TYPE", "COUNT"):
        assert heading in text
    for absent in ("PID", "CPU %", "MEM %", "UPTIME"):
        assert absent not in text


# -- logs -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "role"),
    [
        ("2025-01-01 [ERROR] it broke", "red"),
        ("2025-01-01 [WARN] careful", "yellow"),
        ("2025-01-01 [DEBUG] noisy", "overlay1"),
        ("2025-01-01 [INFO] fine", "subtext1"),
        ("no level at all", "subtext1"),
    ],
)
def test_a_log_line_is_coloured_by_its_level(line: str, role: str):
    assert line_role(line) == role


def test_the_logs_screen_names_the_app(draw):
    assert "blog" in draw(Screen.LOGS, "blog")


def test_the_logs_screen_starts_live(draw):
    assert "[LIVE]" in draw(Screen.LOGS, "blog")


def test_the_system_logs_screen_needs_no_app(draw):
    assert "System logs" in draw(Screen.SYSTEM_LOGS)


# -- chat -----------------------------------------------------------------------------


def test_the_console_greets_you(draw):
    assert "Hop3 console." in draw(Screen.CHAT)


def test_the_command_list_is_not_empty():
    assert "help" in chat_screen.COMMANDS
    assert "apps" in chat_screen.COMMANDS


@pytest.mark.parametrize(
    ("prefix", "expected"),
    [("he", "help"), ("ap", "apps"), ("res", "restart"), ("cl", "clear")],
)
def test_a_prefix_suggests_the_command_it_could_become(prefix: str, expected: str):
    assert chat_screen.suggest(prefix) == expected


def test_a_complete_command_suggests_nothing_further():
    assert chat_screen.suggest("help") is None


def test_an_unknown_prefix_suggests_nothing():
    assert chat_screen.suggest("zzz") is None


def test_an_empty_prefix_suggests_nothing():
    assert chat_screen.suggest("") is None


@pytest.mark.asyncio
async def test_help_lists_the_commands(hop3):
    printed = await chat_screen.run_command(hop3, "help")

    assert "help" in printed[0].text


@pytest.mark.asyncio
async def test_status_reports_the_connection(hop3):
    printed = await chat_screen.run_command(hop3, "status")

    assert "connecting" in printed[0].text


@pytest.mark.asyncio
async def test_an_unknown_command_says_so(hop3):
    printed = await chat_screen.run_command(hop3, "wibble")

    assert printed[0].kind == "err"
    assert "unknown command" in printed[0].text


@pytest.mark.asyncio
async def test_an_empty_command_prints_nothing(hop3):
    assert await chat_screen.run_command(hop3, "   ") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("verb", ["start", "stop", "restart"])
async def test_a_lifecycle_command_needs_an_app_name(hop3, verb: str):
    printed = await chat_screen.run_command(hop3, verb)

    assert printed[0].kind == "err"
    assert "usage" in printed[0].text


@pytest.mark.asyncio
async def test_a_command_against_a_dead_server_reports_the_error(hop3):
    """Port 1 has nothing listening, so this exercises the real failure path."""
    printed = await chat_screen.run_command(hop3, "apps")

    assert printed[0].kind == "err"


# -- layout helpers -------------------------------------------------------------------


def test_halves_split_an_even_width_evenly():
    assert halves(80) == (40, 40)


def test_halves_give_the_odd_cell_to_the_left():
    assert halves(81) == (41, 40)


@pytest.mark.parametrize("width", [1, 2, 3, 40, 79, 200])
def test_halves_always_add_back_up(width: int):
    assert sum(halves(width)) == width
