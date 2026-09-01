# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Main Hop3 TUI application.

Textual's `App` carried `MODES`, `SCREENS`, `BINDINGS`, reactive attributes and a
screen stack. Here the same information is a small immutable `Nav` value in `ui.state`
plus a table of render functions: `switch_mode` replaces the mode, `push` appends to
the stack, `pop` drops the last one, and the render function for whatever is on top
gets called. That is the entire navigation model — see `notes/hop3-tui-porting-plan.md`
for why it stayed in the app rather than going into turbodesk.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import NamedTuple
from urllib.parse import urlparse

from hop3_cli.config import get_config as cli_config
from hop3_cli.core.ssh_tunnel import SshTunnel
from turbodesk import UI, Size, Style, View, vcat, zcat
from turbodesk.events import Event, Key, KeyPress

from hop3_tui.api.client import Hop3Client, Hop3ClientError
from hop3_tui.config import TUIConfig, get_config
from hop3_tui.screens import SCREENS, Screen
from hop3_tui.screens._common import poll
from hop3_tui.widgets import footer, header

TITLE = "Hop3"
HEALTH_CHECK_SECONDS = 30.0
MAX_FAILURES_BEFORE_DISCONNECT = 3

MODE_KEYS: dict[str, Screen] = {
    "d": Screen.DASHBOARD,
    "a": Screen.APPS,
    "s": Screen.SYSTEM,
    "o": Screen.ADDONS,
    "b": Screen.BACKUPS,
    "c": Screen.CHAT,
}

FOOTER_BINDINGS = [
    ("d", "Dashboard"),
    ("a", "Apps"),
    ("s", "System"),
    ("o", "Addons"),
    ("b", "Backups"),
    ("c", "Chat"),
    ("?", "Help"),
    ("q", "Quit"),
]

HELP_TEXT = (
    "Navigation: d=Dashboard, a=Apps, s=System, o=Addons, b=Backups, c=Chat\n"
    "Actions: q=Quit, ?=Help"
)


class ConnectionState(Enum):
    """Connection state to the Hop3 server."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"


INDICATORS = {
    ConnectionState.CONNECTED: "● Connected",
    ConnectionState.DISCONNECTED: "● Disconnected",
    ConnectionState.CONNECTING: "● Connecting...",
}


class Nav(NamedTuple):
    """Where we are: a mode, plus any screens pushed on top of it.

    A tuple rather than a list because `ui.state` compares by value to decide whether
    to redraw — a mutated list would look like no change at all.
    """

    mode: Screen = Screen.DASHBOARD
    stack: tuple[tuple[Screen, str], ...] = ()

    @property
    def current(self) -> tuple[Screen, str]:
        """The screen actually on show, and its argument."""
        return self.stack[-1] if self.stack else (self.mode, "")

    def switch(self, mode: Screen) -> Nav:
        return Nav(mode, ())

    def push(self, screen: Screen, argument: str = "") -> Nav:
        return Nav(self.mode, (*self.stack, (screen, argument)))

    def pop(self) -> Nav:
        return Nav(self.mode, self.stack[:-1])


def _tunnel_hint(server: str) -> str:
    """Why a request over a tunnel can fail in a way the URL does not explain.

    hop3-server installs the `hop3` user's key with `no-port-forwarding` (it is the
    git-push key), so a tunnel as that user connects and then refuses every channel
    — which arrives here as a bare read error. `hop3` itself tunnels as root.
    """
    return (
        f"(over an SSH tunnel to {server}; if the SSH user's authorized_keys "
        f"carries no-port-forwarding — hop3-server sets that on the `hop3` user — "
        f"forwarding is refused. hop3-cli connects as root.)"
    )


def open_tunnel(server: str) -> tuple[SshTunnel, str]:
    """Forward a local port to hop3-server on the far side of `server`.

    hop3-cli reaches an `ssh://` target this way and rewrites its RPC URL to the
    local end (`hop3_cli.rpc.client.Client`); the TUI does the same, with the same
    `SshTunnel`, so both arrive at the same server by the same route.
    """
    parsed = urlparse(server)
    if not parsed.hostname:
        msg = f"SSH server URL has no hostname: {server!r}"
        raise ValueError(msg)
    cli = cli_config()
    tunnel = SshTunnel(
        parsed.hostname,
        cli.get("server_port", 8000),
        user=parsed.username or cli.get("ssh_user", "root"),
        ssh_port=parsed.port or 22,
        key=key if isinstance(key := cli.get("ssh_key", None), str) else None,
    )
    tunnel.start()
    return tunnel, f"http://localhost:{tunnel.local_bind_port}"


class Hop3TUI:
    """Holds what outlives a frame: the client, the config, the failure count."""

    def __init__(self, config: TUIConfig | None = None) -> None:
        self.config = config or get_config()
        #: Held open for the life of the app when the server is reached over SSH.
        self.tunnel: SshTunnel | None = None
        base_url = self.config.server_url
        if base_url.startswith("ssh://"):
            self.tunnel, base_url = open_tunnel(base_url)

        self.api_client = Hop3Client(
            base_url=base_url,
            transport_hint=_tunnel_hint(self.config.server_url) if self.tunnel else "",
            token=self.config.auth_token,
            verify_ssl=self.config.verify_ssl,
            ssl_cert=self.config.ssl_cert,
        )
        self.connection_state = ConnectionState.CONNECTING
        self.consecutive_failures = 0

    async def check_connection(self) -> None:
        """Health check: listing apps is the cheapest call that proves the server."""
        self.connection_state = ConnectionState.CONNECTING
        try:
            await self.api_client.list_apps()
        except Hop3ClientError:
            self.mark_api_failure()
        else:
            self.connection_state = ConnectionState.CONNECTED
            self.consecutive_failures = 0

    def close(self) -> None:
        """Drop the tunnel, if we opened one. Safe to call twice."""
        if self.tunnel is not None:
            self.tunnel.stop()
            self.tunnel = None

    def mark_api_success(self) -> None:
        self.connection_state = ConnectionState.CONNECTED
        self.consecutive_failures = 0

    def mark_api_failure(self) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= MAX_FAILURES_BEFORE_DISCONNECT:
            self.connection_state = ConnectionState.DISCONNECTED


def app(hop3: Hop3TUI) -> Callable[[UI], View]:
    """Build the render function for `hop3`."""

    def render(ui: UI) -> View:
        nav: Nav
        nav, set_nav = ui.state(Nav())
        poll(ui, HEALTH_CHECK_SECONDS, hop3.check_connection)

        def keys(event: Event) -> bool:
            if not isinstance(event, KeyPress):
                return False
            match event.key:
                case "q":
                    ui.exit()
                case "?":
                    ui.notify(HELP_TEXT, seconds=5)
                case Key.ESCAPE if nav.stack:
                    set_nav(nav.pop())
                case Key.ESCAPE if nav.mode is not Screen.DASHBOARD:
                    # The original's `go_back`. A screen with a focused text input —
                    # chat, or a filter — legitimately swallows the letter keys, so
                    # there has to be a way out that is not a letter.
                    set_nav(nav.switch(Screen.DASHBOARD))
                case key if isinstance(key, str) and key in MODE_KEYS and not nav.stack:
                    set_nav(nav.switch(MODE_KEYS[key]))
                case _:
                    return False
            return True

        ui.on_event(keys)

        screen, argument = nav.current
        chrome_height = 2
        body_size = Size(ui.size.width, max(1, ui.size.height - chrome_height))
        # Each screen keeps its own hook slots: they are matched between frames by call
        # order, and switching screens changes that order. Without the scope, one
        # screen's `ui.state` slot is handed to whatever the next screen calls first.
        with ui.scope(screen):
            body = SCREENS[screen](
                ui,
                hop3,
                body_size,
                argument=argument,
                push=lambda s, a="": set_nav(nav.push(s, a)),
                switch=lambda m: set_nav(nav.switch(m)),
            )
        body = body.crop(bottom=max(0, body.height - body_size.height))

        return zcat([
            vcat([
                header(ui, TITLE, INDICATORS[hop3.connection_state]),
                body,
                footer(ui, _bindings(nav)),
            ]),
            View.rect(*ui.size, Style(bg=ui.theme.base)),
        ])

    return render


def _bindings(nav: Nav) -> list[tuple[str, str]]:
    return [("esc", "Back"), *FOOTER_BINDINGS] if nav.stack else FOOTER_BINDINGS
