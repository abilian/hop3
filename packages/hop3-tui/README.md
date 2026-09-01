# hop3-tui

Terminal User Interface for Hop3 PaaS.

## Overview

A modern, keyboard-driven terminal interface for managing Hop3 applications, built with [turbodesk](https://pypi.org/project/turbodesk/).

## Features

- **Dashboard overview**: System stats, app summary, recent activity
- **Application management**: List, filter, start/stop/restart apps
- **Environment variables**: View, add, edit, delete with sensitive value hiding
- **Live log polling**: Filter logs, pause/resume, auto-scroll
- **Chat interface**: Interactive command line with tab completion
- **System monitoring**: CPU, memory, disk usage and service status
- **Addon management**: Create, attach, detach PostgreSQL, Redis, MySQL
- **Backup management**: Create, restore, delete app backups
- **Connection status indicator**: Visual feedback for server connectivity

## Installation

```bash
pip install hop3-tui
```

## Quick Start

```bash
# Set your server URL
export HOP3_SERVER_URL="https://hop3.example.com"
export HOP3_TOKEN="your-api-token"

# Run the TUI
hop3-tui
```

## Configuration

Configuration via environment variables or `~/.config/hop3/tui.toml`:

| Variable | Description | Default |
|----------|-------------|---------|
| `HOP3_SERVER_URL` | Server URL | `http://localhost:5000` |
| `HOP3_TOKEN` | API authentication token | - |
| `HOP3_TUI_THEME` | Color theme (`dark`/`light`) | `dark` |

### Config File

```toml
[server]
url = "https://hop3.example.com"
token = "your-api-token"

[display]
theme = "dark"
refresh_interval = 5
```

## Keyboard Shortcuts

### Global

| Key | Action |
|-----|--------|
| `d` | Dashboard |
| `a` | Apps list |
| `s` | System status |
| `o` | Addons |
| `b` | Backups |
| `c` | Chat interface |
| `?` | Help |
| `q` | Quit |

### Navigation

| Key | Action |
|-----|--------|
| `j`/`Down` | Move down |
| `k`/`Up` | Move up |
| `Enter` | Select |
| `Escape` | Go back |
| `/` | Filter |
| `R` | Refresh |

### Apps

| Key | Action |
|-----|--------|
| `s` | Start app |
| `S` | Stop app |
| `r` | Restart app |
| `l` | View logs |
| `e` | Environment variables |

## Architecture

```
hop3-tui/
├── src/hop3_tui/
│   ├── __main__.py       # Entry point
│   ├── app.py            # Main Hop3TUI class with connection state
│   ├── config.py         # Configuration loading (env vars + TOML)
│   ├── api/
│   │   ├── client.py     # JSON-RPC client with error handling
│   │   └── models.py     # Pydantic data models
│   ├── screens/          # One `render(ui, hop3, size, ...) -> View` per screen
│   │   ├── _common.py    # bind(), halves(), rows(), fill() — what CSS used to do
│   │   ├── _logview.py   # The pane behind both logs.py and system_logs.py
│   │   ├── dashboard.py  # Overview with app counts
│   │   ├── apps.py       # App list and management
│   │   ├── app_detail.py # Single app view
│   │   ├── logs.py       # Live log polling
│   │   ├── env_vars.py   # Environment variable editor
│   │   ├── system.py     # System status
│   │   ├── addons.py     # Addon management
│   │   ├── backups.py    # Backup management
│   │   ├── processes.py  # Running processes
│   │   ├── system_logs.py# System-wide logs
│   │   └── chat.py       # Command interface
│   └── widgets/
│       ├── chrome.py        # Header, footer, panel frames
│       ├── status_panel.py  # Resource meters
│       ├── status_badge.py  # Status indicators
│       └── util.py          # Bar gauges, and the "not reported" marker
└── tests/                # pytest test suite (235 tests)
```

### Immediate mode

There is no widget tree. The app is a function `(UI) -> View` that turbodesk re-runs
whenever a frame is marked dirty, and a screen is a function of its arguments — so
there is no `compose()`, no `reactive`/`watch_*`, no `query_one`, and no stylesheet.
Layout is arithmetic (`halves`, `rows`), and state lives in `ui.state` hooks matched
between frames by call order. Each screen renders inside its own `ui.scope`, which is
what keeps those slots from being handed to the next screen on a switch.

Rendering has no side effect on the screen, so a test calls the app function at any
size and asserts on what came out — no pilot, no event loop, no async harness:

```python
to_text(render(app(hop3), size=Size(90, 26)))
```

### Nothing is invented

A panel shows what the server reported or says that it does not know
(`not reported by the server`); it never shows a plausible-looking constant. The log
pane's heading drops from `LIVE` to `UNREACHABLE` when a poll fails, rather than
going on looking live over a dead connection. `tests/test_no_fabricated_data.py`
holds that line.

### Connection Handling

The TUI tracks connection state to the Hop3 server:

- **Connected** (green indicator): Server is reachable
- **Disconnected** (red indicator): Connection lost, will retry
- **Connecting** (yellow indicator): Attempting to connect

Connection failures are tracked and the state updates automatically. The UI continues to show cached data while disconnected.

## Development

```bash
# Run it
uv run hop3-tui

# Run tests (from the workspace root)
uv run pytest packages/hop3-tui/tests

# Lint and format
uv run ruff check src/
uv run ruff format src/
```

## Documentation

- [User Guide](../../docs/src/guide.md)

## Related Packages

- [hop3-server](../hop3-server/) - The server that hop3-tui communicates with
- [hop3-cli](../hop3-cli/) - Alternative command-line interface

## License

Apache-2.0 - Copyright (c) 2024-2026, Abilian SAS
