# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The TUI must show what the server said, or say that it does not know.

Every screen here used to render invented data behind a normal-looking UI: the
log pane served a hardcoded sample and appended a new fake line roughly every
three seconds, and the system screen reported three constants as live metrics
with four services permanently RUNNING. None of it failed, which is why it
lasted — so these tests assert the absence of the specific fabrications as well
as the presence of the real values.
"""

from __future__ import annotations

import pytest
from hop3_tui.screens.logs import LogsScreen
from hop3_tui.screens.system import (
    UNAVAILABLE,
    ResourcesPanel,
    ServicesPanel,
    SystemInfoPanel,
)
from textual.app import App, ComposeResult
from textual.widgets import Static


class StubClient:
    """Records the call and hands back whatever the test set up."""

    def __init__(self, lines: list[str] | None = None, error: Exception | None = None):
        self.lines = lines or []
        self.error = error
        self.calls: list[tuple[str, int]] = []

    async def get_app_logs(self, name: str, lines: int = 100) -> list[str]:
        self.calls.append((name, lines))
        if self.error:
            raise self.error
        return self.lines


class StubApp(App):
    """An app exposing `api_client`, which is what LogsScreen looks for."""

    def __init__(self, screen: LogsScreen, client: StubClient | None) -> None:
        super().__init__()
        self._screen = screen
        if client is not None:
            self.api_client = client

    def compose(self) -> ComposeResult:
        yield self._screen


def _rendered(screen: LogsScreen) -> str:
    return str(screen.query_one("#logs-content", Static).content)


# ---------- the log pane ------------------------------------------------


@pytest.mark.asyncio
async def test_log_pane_shows_the_servers_lines():
    screen = LogsScreen(app_name="myapp")
    client = StubClient(lines=["10:00:00 [INFO] real line", ""])

    async with StubApp(screen, client).run_test():
        # Mounting alone must reach the server: the pane used to fill itself
        # from a literal and never call anything.
        assert client.calls == [("myapp", 100)]

        await screen._fetch_logs()

        assert client.calls[-1] == ("myapp", 100)
        assert screen._logs == ["10:00:00 [INFO] real line"]  # blank line dropped
        assert "real line" in _rendered(screen)


@pytest.mark.asyncio
async def test_log_pane_invents_nothing_when_the_app_has_no_logs():
    """The fabricated sample used to fill exactly this case."""
    screen = LogsScreen(app_name="quiet-app")

    async with StubApp(screen, StubClient(lines=[])).run_test():
        await screen._fetch_logs()

        assert screen._logs == []
        rendered = _rendered(screen)
        assert "quiet-app has not logged anything yet." in rendered
        # The specific lines the pane used to invent.
        assert "Failed to connect to redis" not in rendered
        assert "New log entry" not in rendered


@pytest.mark.asyncio
async def test_log_pane_says_so_when_there_is_no_server():
    screen = LogsScreen(app_name="myapp")

    async with StubApp(screen, None).run_test():
        await screen._fetch_logs()

        assert screen._logs == []
        assert "Not connected to a server" in _rendered(screen)


@pytest.mark.asyncio
async def test_log_pane_says_so_when_no_app_is_selected():
    """`logs` is a registered mode, so the screen exists with no app name."""
    screen = LogsScreen()

    async with StubApp(screen, StubClient(lines=["never fetched"])).run_test():
        await screen._fetch_logs()

        assert screen._logs == []
        assert "No app selected" in _rendered(screen)


@pytest.mark.asyncio
async def test_a_failed_fetch_reports_itself_and_keeps_what_it_had():
    """A blink of RPC failure must not blank a pane someone is reading."""
    screen = LogsScreen(app_name="myapp")
    client = StubClient(lines=["10:00:00 [INFO] real line"])

    async with StubApp(screen, client).run_test():
        await screen._fetch_logs()
        client.error = RuntimeError("connection refused")
        await screen._fetch_logs()

        assert screen._logs == ["10:00:00 [INFO] real line"]
        assert "connection refused" in screen._empty_reason


# ---------- the system screen -------------------------------------------


@pytest.mark.asyncio
async def test_resources_report_no_measurement_rather_than_a_number():
    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield ResourcesPanel()

    app = TestApp()
    async with app.run_test():
        panel = app.query_one(ResourcesPanel)
        rendered = str(panel.query_one("#resources-content", Static).content)

        assert panel.cpu is None
        assert rendered.count(UNAVAILABLE) == 3
        # The three constants the panel used to assert on a 5-second timer.
        assert "42%" not in rendered
        assert "63%" not in rendered
        assert "81%" not in rendered


@pytest.mark.asyncio
async def test_resources_render_a_measurement_when_there_is_one():
    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield ResourcesPanel()

    app = TestApp()
    async with app.run_test():
        panel = app.query_one(ResourcesPanel)
        panel.cpu = 12.0
        panel.memory = 0.0
        rendered = str(panel.query_one("#resources-content", Static).content)

        assert "12%" in rendered
        # 0% is a measurement, not a missing one.
        assert "Memory: " in rendered
        assert "0%" in rendered


@pytest.mark.asyncio
async def test_services_panel_shows_what_it_was_given():
    """It used to discard this dict and render four services as RUNNING."""

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield ServicesPanel()

    app = TestApp()
    async with app.run_test():
        panel = app.query_one(ServicesPanel)
        panel.update_services({"nginx": False})
        rendered = str(panel.query_one("#services-content", Static).content)

        assert "nginx" in rendered
        assert "STOPPED" in rendered
        assert "postgresql" not in rendered
        assert "RUNNING" not in rendered


@pytest.mark.asyncio
async def test_services_panel_claims_nothing_before_it_is_told():
    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield ServicesPanel()

    app = TestApp()
    async with app.run_test():
        panel = app.query_one(ServicesPanel)
        rendered = str(panel.query_one("#services-content", Static).content)

        assert rendered == UNAVAILABLE
        assert "RUNNING" not in rendered


@pytest.mark.asyncio
async def test_system_info_does_not_invent_a_host():
    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield SystemInfoPanel()

    app = TestApp()
    async with app.run_test():
        panel = app.query_one(SystemInfoPanel)
        rendered = str(panel.query_one("#info-content", Static).content)

        assert "hop3.dev" not in rendered
        assert "v0.5.0" not in rendered
        assert "14d 3h 22m" not in rendered
        assert rendered.count(UNAVAILABLE) == 3
