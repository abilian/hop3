# hop3-tui Deep Dive

This document provides detailed internal documentation for the hop3-tui package. For a quick overview, see the [package overview](index.md).

## Architecture Overview

hop3-tui is a terminal user interface built with Textual. It provides:

1. **Dashboard** - System overview and quick actions
2. **App Management** - List, control, and monitor applications
3. **Log Viewer** - Paginated log retrieval
4. **Chat Interface** - Command-line with auto-completion
5. **System Monitoring** - CPU, memory, disk status

## Module Structure

```
hop3_tui/
├── __init__.py
├── __main__.py          # Entry point (main())
├── app.py               # Main Hop3TUI class
├── config.py            # Configuration handling (TUIConfig)
├── api/
│   ├── client.py        # JSON-RPC client (httpx)
│   └── models.py        # Pydantic data models
├── screens/
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
├── widgets/
│   ├── status_badge.py  # Status indicator
│   ├── status_panel.py  # System status panel
│   └── confirmation.py  # Confirmation dialog
└── styles/
    └── base.tcss        # Global CSS styles
```

## Textual Framework

hop3-tui uses [Textual](https://textual.textualize.io/) for the TUI:

### Main Application

```python
class Hop3TUI(App[str]):
    """Hop3 Terminal User Interface Application."""

    CSS_PATH = "styles/base.tcss"

    BINDINGS: ClassVar = [
        Binding("q", "quit", "Quit", show=True),
        Binding("?", "help", "Help", show=True),
        Binding("d", "switch_mode('dashboard')", "Dashboard", show=True),
        Binding("a", "switch_mode('apps')", "Apps", show=True),
        Binding("s", "switch_mode('system')", "System", show=True),
        Binding("o", "switch_mode('addons')", "Addons", show=True),
        Binding("b", "switch_mode('backups')", "Backups", show=True),
        Binding("c", "switch_mode('chat')", "Chat", show=True),
    ]

    # Top-level views, swapped with switch_mode()
    MODES: ClassVar = {
        "dashboard": DashboardScreen,
        "apps": AppsScreen,
        "system": SystemScreen,
        "addons": AddonsScreen,
        "backups": BackupsScreen,
        "chat": ChatScreen,
    }

    # Screens pushed onto the stack (app detail, logs)
    SCREENS: ClassVar = {
        "app_detail": AppDetailScreen,
        "logs": LogsScreen,
    }

    def on_mount(self) -> None:
        self.switch_mode("dashboard")
```

Top-level views are registered in `MODES` and swapped with `switch_mode()`; transient screens (app detail, log viewer) are pushed with `push_screen()`.

### Screen Pattern

Each screen is a Textual `Screen`:

```python
class AppsScreen(Screen):
    """Applications list screen."""

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("enter", "select_app", "Details"),
    ]

    def compose(self) -> ComposeResult:
        yield DataTable()
        yield FilterInput()

    async def on_mount(self) -> None:
        await self.load_apps()

    async def load_apps(self) -> None:
        apps = await self.app.api_client.list_apps()
        self.populate_table(apps)
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
| Running: 5                       | CPU:    ████░░░░░░ 42%           |
| Stopped: 2                       | Memory: ██████░░░░ 63%           |
| Failed:  1                       | Disk:   ████████░░ 81%           |
+----------------------------------+----------------------------------+
| RECENT ACTIVITY                  | QUICK ACTIONS                    |
| ├─ myapp deployed                | [d] Deploy new app               |
| ├─ api restarted                 | [b] Create backup                |
| └─ worker stopped                | [l] View system logs             |
+----------------------------------+----------------------------------+
```

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

REPL-style command interface built on a Textual `Input` with a custom
`Suggester`:

```python
class ChatScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="chat-container"):
            yield Static(id="chat-messages")
        with Static(id="input-bar"):
            yield Input(id="command-input", suggester=self._suggester)
        yield Footer()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "command-input":
            return
        self._process_command(event.value.strip())
```

Tab completion is provided by a `Suggester` subclass. The first word is
completed against a static command list; the second word, for app-related
commands, is completed against app names fetched via `list_apps()`:

```python
COMMANDS = [
    "apps", "app", "start", "stop", "restart", "logs",
    "env", "status", "clear", "help", "deploy", "backup", "restore",
]

class CommandSuggester(Suggester):
    async def get_suggestion(self, value: str) -> str | None:
        parts = value.split()
        if len(parts) == 1:  # complete the command
            prefix = parts[0].lower()
            return next(
                (c for c in COMMANDS if c.startswith(prefix) and c != prefix), None
            )
        if len(parts) == 2 and parts[0].lower() in APP_COMMANDS:
            prefix = parts[1].lower()
            for name in self._app_names:
                if name.lower().startswith(prefix):
                    return f"{parts[0]} {name}"
        return None
```

## Styling

Textual CSS in `styles/base.tcss`:

```css
/* Global styles */
Screen {
    background: $surface;
}

DataTable {
    height: 100%;
}

DataTable > .datatable--header {
    background: $primary;
}

.status-running {
    color: $success;
}

.status-stopped {
    color: $warning;
}

.status-failed {
    color: $error;
}
```

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

Updates are poll-based. The app runs a periodic health check
(`set_interval(30, ...)`) and screens refresh by re-fetching from the server;
the dashboard re-reads app state on its `refresh_interval`.

### Polling Mode

```python
async def poll_updates(self) -> None:
    """Poll server for updates."""
    while True:
        apps = await self.api_client.list_apps()
        self.update_display(apps)
        await asyncio.sleep(self.config.refresh_interval)
```

WebSocket / push streaming is not implemented; there is no streaming RPC
endpoint and no WebSocket dependency. All refreshes go through the same
poll-and-fetch path.

## Testing

### Unit Tests

```python
async def test_api_client():
    """Test API client methods."""
    client = Hop3Client("http://localhost:5000")
    apps = await client.list_apps()
    assert isinstance(apps, list)
```

### Screen Tests

```python
async def test_dashboard_screen():
    """Test dashboard screen rendering."""
    async with Hop3TUI().run_test() as pilot:
        await pilot.press("d")  # Go to dashboard
        assert pilot.app.screen.name == "dashboard"
```

## Performance

The TUI keeps work off the UI thread by running network calls as Textual
workers (`run_worker`) and refreshing on an interval rather than continuously.
Data is fetched per screen on demand rather than all at once. Pagination,
response caching, and input debouncing are design goals for large deployments
and are not yet implemented across all screens.
