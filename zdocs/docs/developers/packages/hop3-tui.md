# hop3-tui Deep Dive

This document provides detailed internal documentation for the hop3-tui package. For a quick overview, see the [package README](../README.md).

## Architecture Overview

hop3-tui is a terminal user interface built with Textual. It provides:

1. **Dashboard** - System overview and quick actions
2. **App Management** - List, control, and monitor applications
3. **Log Viewer** - Real-time log streaming
4. **Chat Interface** - Command-line with auto-completion
5. **System Monitoring** - CPU, memory, disk status

## Module Structure

```
hop3_tui/
├── __init__.py
├── __main__.py          # Entry point
├── app.py               # Main Hop3TUI class
├── config.py            # Configuration handling
├── api/
│   ├── client.py        # JSON-RPC client (httpx)
│   └── models.py        # Pydantic data models
├── screens/
│   ├── dashboard.py     # Main dashboard
│   ├── apps.py          # Applications list
│   ├── app_detail.py    # App detail view
│   ├── env_vars.py      # Environment variables
│   ├── logs.py          # Log viewer
│   ├── system.py        # System status
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
class Hop3TUI(App):
    """Main TUI application."""

    BINDINGS = [
        ("d", "switch_screen('dashboard')", "Dashboard"),
        ("a", "switch_screen('apps')", "Apps"),
        ("s", "switch_screen('system')", "System"),
        ("c", "switch_screen('chat')", "Chat"),
        ("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()

    async def on_mount(self) -> None:
        self.push_screen(DashboardScreen())
```

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
        apps = await self.app.api.apps_list()
        self.populate_table(apps)
```

## API Client

Async HTTP client using httpx:

```python
class Hop3APIClient:
    """Async JSON-RPC client for hop3-server."""

    def __init__(self, base_url: str, token: str | None = None):
        self.base_url = base_url
        self.token = token
        self._client = httpx.AsyncClient()

    async def call(self, method: str, **params) -> Any:
        """Make RPC call."""
        response = await self._client.post(
            f"{self.base_url}/rpc",
            json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1},
            headers=self._headers(),
        )
        return self._parse_response(response)

    # Typed methods
    async def apps_list(self) -> list[AppInfo]:
        return await self.call("apps.list")

    async def apps_start(self, name: str) -> None:
        return await self.call("apps.start", name=name)
```

## Data Models

Pydantic models for type safety:

```python
class AppInfo(BaseModel):
    """Application information."""
    name: str
    state: AppState
    port: int | None
    runtime: str | None
    updated_at: datetime | None

class SystemStatus(BaseModel):
    """System status information."""
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    services: dict[str, ServiceStatus]
```

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
| ├─ myapp deployed               | [d] Deploy new app               |
| ├─ api restarted                | [b] Create backup                |
| └─ worker stopped               | [l] View system logs             |
+----------------------------------+----------------------------------+
```

### Apps Screen

Features:
- Sortable data table
- Real-time status updates
- Filter/search
- Keyboard shortcuts for actions

### Log Viewer

Features:
- Real-time streaming (WebSocket or polling)
- Pause/resume
- Level filtering (INFO, WARN, ERROR)
- Search within logs
- Download logs

### Chat Interface

REPL-style command interface:

```python
class ChatScreen(Screen):
    def compose(self) -> ComposeResult:
        yield RichLog(id="output")
        yield CommandInput(id="input")

    async def on_command_input_submitted(self, event: CommandInput.Submitted):
        command = event.value
        result = await self.execute_command(command)
        self.query_one("#output").write(result)
```

Tab completion:
```python
COMMANDS = ["apps", "start", "stop", "restart", "logs", "env", "deploy", ...]

async def complete(self, prefix: str) -> list[str]:
    """Get completions for prefix."""
    # Complete commands
    matches = [c for c in COMMANDS if c.startswith(prefix)]

    # Complete app names
    if len(prefix.split()) > 1:
        apps = await self.api.apps_list()
        app_names = [a.name for a in apps]
        matches.extend([n for n in app_names if n.startswith(prefix.split()[-1])])

    return matches
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

```python
def load_config() -> Config:
    """Load configuration from multiple sources."""
    config = Config()

    # 1. Config file
    for path in CONFIG_PATHS:
        if path.exists():
            config.update_from_file(path)
            break

    # 2. Environment variables
    config.update_from_env()

    return config

CONFIG_PATHS = [
    Path("./hop3-tui.toml"),
    Path("./.hop3-tui.toml"),
    Path("~/.config/hop3/tui.toml").expanduser(),
    Path("~/.hop3/tui.toml").expanduser(),
]
```

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

### Polling Mode

```python
async def poll_updates(self) -> None:
    """Poll server for updates."""
    while True:
        apps = await self.api.apps_list()
        self.update_display(apps)
        await asyncio.sleep(self.config.refresh_interval)
```

### WebSocket Mode (planned)

```python
async def stream_updates(self) -> None:
    """Stream updates via WebSocket."""
    async with websockets.connect(f"{self.ws_url}/stream") as ws:
        async for message in ws:
            event = json.loads(message)
            self.handle_event(event)
```

## Testing

### Unit Tests

```python
async def test_api_client():
    """Test API client methods."""
    client = Hop3APIClient("http://localhost:8000")
    apps = await client.apps_list()
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

- **Lazy loading** - Don't load all data upfront
- **Pagination** - Large lists are paginated
- **Caching** - Cache API responses briefly
- **Debouncing** - Debounce rapid user input
