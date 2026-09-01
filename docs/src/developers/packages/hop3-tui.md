# hop3-tui Deep Dive

This document provides detailed internal documentation for the hop3-tui package. For a quick overview, see the [package overview](index.md).

## Architecture Overview

hop3-tui is a terminal user interface built with [turbodesk](https://pypi.org/project/turbodesk/). It provides:

1. **Dashboard** - System overview and quick actions
2. **App Management** - List, control, and monitor applications
3. **Log Viewer** - Polled log retrieval
4. **Chat Interface** - Command-line with auto-completion
5. **System Monitoring** - CPU, memory, disk status

## Module Structure

```
hop3_tui/
├── __init__.py
├── __main__.py          # Entry point (main())
├── app.py               # Nav state, key bindings, connection state
├── config.py            # Configuration handling (TUIConfig)
├── api/
│   ├── client.py        # JSON-RPC client (httpx)
│   └── models.py        # Pydantic data models
├── screens/
│   ├── __init__.py      # The Screen enum and the dispatch table
│   ├── _common.py       # bind(), halves(), rows(), fill() — what CSS used to do
│   ├── _logview.py      # The pane behind both log screens
│   ├── dashboard.py     # Main dashboard
│   ├── apps.py          # Applications list
│   ├── app_detail.py    # App detail view
│   ├── env_vars.py      # Environment variables
│   ├── logs.py          # App log viewer
│   ├── system.py        # System status
│   ├── system_logs.py   # System log viewer
│   ├── processes.py     # Process list
│   ├── addons.py        # Addons management
│   ├── backups.py       # Backups management
│   └── chat.py          # Chat interface
└── widgets/
    ├── chrome.py        # Header, footer, panel frames
    ├── status_badge.py  # Status indicator
    ├── status_panel.py  # System status panel
    └── util.py          # Bar gauges, and the "not reported" marker
```

## Immediate mode

turbodesk has no widget tree. The whole app is a function `(UI) -> View` re-run
whenever a frame is marked dirty — state changed, an event arrived, the terminal
resized, a timer fired — and the runtime diffs the returned grid row by row. Nothing
survives a frame except hook slots, so there is no `compose()`, no `reactive`, no
`watch_*`, no `query_one`, and no stylesheet. A `View` is an immutable grid of styled
cells composed with `hcat`, `vcat` and `zcat`; layout is arithmetic and styles are
`Style` values in Python.

### Main Application

`app.py` holds no widget state. Navigation is one immutable `Nav` value in `ui.state`
— a mode plus a stack of pushed screens — and a table of render functions:

```python
class Nav(NamedTuple):
    """Where we are: a mode, plus any screens pushed on top of it."""

    mode: Screen = Screen.DASHBOARD
    stack: tuple[tuple[Screen, str], ...] = ()

    @property
    def current(self) -> tuple[Screen, str]:
        return self.stack[-1] if self.stack else (self.mode, "")


def app(hop3: Hop3TUI) -> Callable[[UI], View]:
    def render(ui: UI) -> View:
        nav, set_nav = ui.state(Nav())
        ui.every(HEALTH_CHECK_SECONDS, hop3.check_connection)
        ui.on_event(keys)

        screen, argument = nav.current
        # Each screen keeps its own hook slots: they are matched between frames by
        # call order, and switching screens changes that order.
        with ui.scope(screen):
            body = SCREENS[screen](ui, hop3, body_size, argument=argument, ...)

        return zcat([vcat([header(...), body, footer(...)]), ...])

    return render
```

`Hop3TUI` is now only what outlives a frame: the API client, the config, and the
consecutive-failure count behind the connection indicator.

The `ui.scope(screen)` is load-bearing. Hook slots (`ui.state`, `ui.every`) are matched
between frames **by call order**, so without a per-screen scope, switching screens
hands one screen's state slot to whatever the next screen calls first.

### Screen Pattern

A screen is a function with a fixed signature returning a `View`. Key bindings are a
dict, which is what Textual's `BINDINGS` list plus its `action_*` naming convention
amounted to:

```python
def render(
    ui: UI,
    hop3,
    size: Size,
    *,
    argument: str = "",
    push: Callable[..., None] | None = None,
    switch: Callable[[Screen], None] | None = None,
) -> View:
    apps, set_apps = ui.state(NO_APPS)

    async def refresh() -> None:
        try:
            fetched = await hop3.api_client.list_apps()
        except Hop3ClientError as error:
            ui.notify(f"Server error: {error}", kind="error", seconds=5)
        else:
            set_apps(tuple(fetched))

    ui.every(15.0, refresh)
    bind(ui, {"r": lambda: ui.spawn(refresh()), "l": lambda: push(Screen.LOGS, name)})

    return fill(ui, table(ui, COLUMNS, rows, ...), size)
```

Modal dialogs are awaited rather than mounted, so there is no pending-action state to
carry between a dialog and its response handler:

```python
async def ask() -> None:
    if await dialog.confirm(ui, "Delete add-on", f"Delete {name}?", yes="Delete"):
        await hop3.api_client.delete_addon(name)

ui.spawn(ask())
```

## API Client

Async HTTP client using httpx. The TUI talks to the same JSON-RPC endpoint
as `hop3-cli`: a single `cli` method that forwards the CLI argv (`cli_args`)
to the server. The TUI therefore shares the server's command surface, and
each typed client method is a thin wrapper that builds the matching argv.

```python
class Hop3Client:
    """Client for communicating with Hop3 server via JSON-RPC."""

    def __init__(
        self,
        base_url: str = "http://localhost:5000",
        token: str | None = None,
        verify_ssl: bool = True,
        ssl_cert: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        ...

    async def _rpc_call(
        self,
        cli_args: list[str],
        extra_args: dict[str, Any] | None = None,
    ) -> Any:
        """Make a JSON-RPC call (method "cli") to the server."""
        payload = {
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {"cli_args": cli_args, "extra_args": extra_args or {}},
            "id": self._next_request_id(),
        }
        async with httpx.AsyncClient(verify=self._verify) as client:
            response = await client.post(
                f"{self.base_url}/rpc", json=payload, headers=self._get_headers()
            )
            ...

    # Typed methods wrap CLI argv
    async def list_apps(self) -> list[App]:
        result = await self._rpc_call(["apps"])
        ...

    async def start_app(self, name: str) -> bool:
        await self._rpc_call(["app", "start", name])
        return True
```

Each typed method (`list_apps`, `get_app`, `start_app`, `stop_app`,
`restart_app`, `get_app_logs`, `get_system_status`, `list_addons`,
`list_backups`, `get_env_vars`, ...) builds the corresponding CLI argv and
parses the rich-text payload the server returns (`{"t": "table", ...}` or
`{"t": "text", ...}`).

## Data Models

Pydantic models for type safety (`api/models.py`):

```python
class App(BaseModel):
    """Application model."""
    name: str
    runtime: str = "unknown"
    state: AppState = AppState.STOPPED
    port: int | None = None
    hostname: str | None = None
    workers: int = 1
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

class SystemStatus(BaseModel):
    """System status model."""
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    disk_percent: float = 0.0
    uptime_seconds: int = 0
    hostname: str = "unknown"
    hop3_version: str = "unknown"
    apps_running: int = 0
    apps_stopped: int = 0
    apps_failed: int = 0
```

`AppState` is an enum (`STOPPED`, `STARTING`, `RUNNING`, `STOPPING`, `FAILED`).
The other models are `EnvVar`, `Addon`, and `Backup`.

## Screens Detail

### Dashboard Screen

```
+----------------------------------+----------------------------------+
| APPLICATIONS                     | SYSTEM STATUS                    |
| Running: 5                       | CPU:    not reported by the server|
| Stopped: 2                       | Memory: not reported by the server|
| Failed:  1                       | Disk:   not reported by the server|
+----------------------------------+----------------------------------+
| RECENT ACTIVITY                  | QUICK ACTIONS                    |
| No recent activity               | [d] Deploy new app               |
|                                  | [b] Create backup                |
|                                  | [l] View system logs             |
+----------------------------------+----------------------------------+
```

The system panel is empty because `Hop3Client.get_system_status` makes the RPC call
but does not yet parse the response. It says so rather than showing a number: see
[Nothing is invented](#nothing-is-invented).

### Apps Screen

Features:
- Sortable data table
- Real-time status updates
- Filter/search
- Keyboard shortcuts for actions

### Log Viewer

The viewer retrieves a fixed number of recent lines via
`get_app_logs(name, lines)`, which calls `app logs <name> --lines N` on the
server. Streaming/follow mode is not implemented; refresh re-fetches.

### Chat Interface

REPL-style command interface over turbodesk's `textbox`. The transcript is a tuple in
`ui.state`; submitting a line appends to it and dispatches:

```python
def render(ui: UI, hop3, size: Size, ...) -> View:
    lines, set_lines = ui.state(NO_LINES)
    box = textbox(ui, focus="command", ...)
    if box.submitted:
        ui.spawn(run_command(box.value))
```

Tab completion is a hint line under the prompt rather than an inline ghost
completion: `textbox` has no suggester hook. The first word is completed against a
static command list; the second, for app-related commands, against app names fetched
via `list_apps()`.

```python
COMMANDS = [
    "apps", "app", "start", "stop", "restart", "logs",
    "env", "status", "clear", "help", "deploy", "backup", "restore",
]
```

## Layout, in place of CSS

There is no stylesheet. Every layout in hop3-tui is a grid of halves or a single
scrolling pane, so `screens/_common.py` covers all of it in about a dozen lines:

```python
def halves(width: int) -> tuple[int, int]:
    """Two columns, the left taking the odd cell. What `grid-size: 2` worked out."""
    left = width // 2 + width % 2
    return left, width - left


def rows(size: Size, *fractions: float) -> list[int]:
    """Split `size.height` into rows by fraction, giving the remainder to the last."""
    heights = [max(1, int(size.height * fraction)) for fraction in fractions[:-1]]
    return [*heights, max(1, size.height - sum(heights))]
```

The dashboard's `layout: grid; grid-size: 2` becomes
`vcat([hcat([a, b]), hcat([c, d])])` over a computed cell size. Colours come from the
theme's role names (`ui.theme.green`, `ui.theme.role("subtext1")`) rather than CSS
variables, and the status-badge rules become a `match` returning a `Style`.

The one cost: a hand-computed panel crops when the terminal is too short, where CSS
would have scrolled. Panels mark the corner with `…` when they crop, so a vanished row
does not read as a data bug.

## Configuration

### Config Loading

Configuration is a frozen-style `TUIConfig` dataclass loaded by
`TUIConfig.load()`. Sources are merged in increasing priority: the hop3-cli
config file (lowest), then the TUI config file, then `HOP3_*` environment
variables (highest).

```python
@dataclass
class TUIConfig:
    server_url: str = "http://localhost:5000"
    auth_token: str | None = None
    verify_ssl: bool = True
    ssl_cert: str | None = None
    theme: str = "dark"
    refresh_interval: int = 5
    show_clock: bool = True
    auto_refresh: bool = True
    confirm_destructive: bool = True

    @classmethod
    def load(cls) -> TUIConfig:
        config = cls()
        if cli_config := cls._find_cli_config_file():
            config = cls._load_from_cli_config(cli_config, config)
        if (config_file := cls._find_config_file()) and config_file.exists():
            config = cls._load_from_file(config_file, config)
        return cls._load_from_env(config)
```

`_find_config_file()` checks these TUI config paths in order:

```python
candidates = [
    Path.cwd() / "hop3-tui.toml",
    Path.cwd() / ".hop3-tui.toml",
    Path.home() / ".config" / "hop3" / "tui.toml",
    Path.home() / ".hop3" / "tui.toml",
]
```

The server URL and auth token can also be inherited from the hop3-cli config
file (`api_url` / `api_token`), and overridden by environment variables
(`HOP3_SERVER_URL`/`HOP3_URL`, `HOP3_AUTH_TOKEN`/`HOP3_TOKEN`,
`HOP3_VERIFY_SSL`, `HOP3_SSL_CERT`, `HOP3_TUI_THEME`, `HOP3_TUI_REFRESH`).

### Config File Format

```toml
[server]
url = "https://hop3.example.com"
token = "..."

[display]
theme = "dark"
refresh_interval = 5
show_clock = true

[behavior]
auto_refresh = true
confirm_destructive = true
```

## Real-Time Updates

Updates are poll-based. Timers are `ui.every(seconds, callback)` hooks, cancelled
automatically when the screen that registered them stops being rendered; a one-off call
is `ui.spawn(coro())`. The app health-checks every 30s, and each screen re-fetches on
its own interval (the dashboard on the configured `refresh_interval`).

```python
async def refresh() -> None:
    try:
        apps = await hop3.api_client.list_apps()
    except Hop3ClientError as error:
        hop3.mark_api_failure()
        ui.notify(f"Server error: {error}", kind="error", seconds=5)
    else:
        hop3.mark_api_success()
        set_counts(AppCounts.of(apps))

ui.every(float(hop3.config.refresh_interval), refresh)
```

WebSocket / push streaming is not implemented; there is no streaming RPC endpoint and
no WebSocket dependency. All refreshes go through the same poll-and-fetch path.

A background task that raises does not fail silently: turbodesk records the failure and
the next render re-raises it, so a broken command cannot look like an unbound key.

## Nothing is invented

A panel shows what the server reported or says that it does not know. It never shows a
plausible-looking constant.

This is not hypothetical tidiness. Before it was fixed, the log pane served eight
hardcoded lines and appended an invented one roughly every three seconds — so it
showed `[ERROR] Failed to connect to redis` for an app that was fine, and the log
download wrote those invented lines to a file an operator could attach to a bug
report. The system screen reported CPU/memory/disk as the constants 42/63/81 on a
timer, four services as `RUNNING` whatever the server said, and a host called
`hop3.dev` running `v0.5.0` with 14 days of uptime.

The rules the code now follows:

- A missing measurement renders as `not reported by the server` (`widgets.util.UNAVAILABLE`).
  `None` means no measurement; `0%` is a measurement and renders as one.
- A services dict of `None` means nothing was reported; `{}` means reported, and empty.
  They read differently on screen.
- The log pane's heading drops from `LIVE` to `UNREACHABLE`, showing the error, when a
  poll fails. It keeps the lines it already had — a blink of RPC failure should not
  blank a pane someone is reading — but it stops claiming to be live.
- Pressing `r` on the system screen says "System metrics are not reported by the server
  yet." rather than "refreshed". Claiming a refresh that fetched nothing is the same
  defect one layer up.

`tests/test_no_fabricated_data.py` asserts the absence of each specific fabrication as
well as the presence of the real values, because none of this ever failed — which is
why it lasted.

## Testing

Rendering has no side effect on the screen, so a test calls the app function at any
size and asserts on what came out. There is no pilot, no event loop and no async
harness.

### Rendering a screen

```python
def draw(screen: Screen, argument: str = "", size: Size = Size(78, 16)) -> str:
    def wrapper(ui):
        with ui.scope(screen):
            return SCREENS[screen](ui, hop3, size, argument=argument, ...)

    return to_text(render(wrapper, size=size))


def test_the_system_screen_invents_no_services():
    text = draw(Screen.SYSTEM)

    assert "RUNNING" not in text
    assert "not reported by the server" in text
```

`render(app, size=..., events=[KeyPress("q")])` feeds input; `to_text` gives the
grid's characters. Geometry is assertable too (`view.width`, `view.height`).

### Testing the pure parts directly

Anything that is a decision rather than a drawing is a plain function, tested as one —
which is most of what used to be spread across `reactive` attributes and `watch_*`
methods:

```python
def test_a_failed_fetch_stops_the_pane_claiming_to_be_live():
    assert status_line(paused=False, problem="down", count=8).label == "UNREACHABLE"
    # Failure outranks paused: neither may hide it.
    assert status_line(paused=True, problem="down", count=8).label == "UNREACHABLE"
```

### Unit Tests

The `api/` layer and `config.py` have no UI dependency and are tested directly:

```python
@pytest.mark.asyncio
async def test_api_client():
    client = Hop3Client("http://localhost:5000")
    apps = await client.list_apps()
    assert isinstance(apps, list)
```

Run the suite from the workspace root:

```bash
uv run pytest packages/hop3-tui/tests
```

## Performance

Network calls run as turbodesk tasks (`ui.every`, `ui.spawn`) rather than blocking a
render, and screens refresh on an interval rather than continuously. Data is fetched
per screen on demand rather than all at once.

Rendering itself is cheap by construction: a frame produces an immutable grid, and the
runtime diffs it row by row, writing escape codes only for rows that changed.

Pagination, response caching, and input debouncing are design goals for large
deployments and are not yet implemented across all screens.
