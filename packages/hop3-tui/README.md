# hop3-tui

Terminal User Interface for Hop3 PaaS.

## Overview

A modern, keyboard-driven terminal interface for managing Hop3 applications, built with [Textual](https://textual.textualize.io/).

## Features

- **Dashboard overview**: System stats, app summary, recent activity
- **Application management**: List, filter, start/stop/restart apps
- **Environment variables**: View, add, edit, delete with sensitive value hiding
- **Real-time log streaming**: Filter logs, pause/resume, auto-scroll
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
│   ├── screens/
│   │   ├── dashboard.py  # Overview with app counts
│   │   ├── apps.py       # App list and management
│   │   ├── app_detail.py # Single app view
│   │   ├── logs.py       # Real-time log streaming
│   │   ├── env_vars.py   # Environment variable editor
│   │   ├── system.py     # System status
│   │   ├── addons.py     # Addon management
│   │   ├── backups.py    # Backup management
│   │   └── chat.py       # Command interface
│   └── widgets/
│       ├── confirmation.py  # Confirmation dialogs
│       ├── status_panel.py  # Resource meters
│       └── status_badge.py  # Status indicators
└── tests/                # pytest test suite (167 tests)
```

### Connection Handling

The TUI tracks connection state to the Hop3 server:

- **Connected** (green indicator): Server is reachable
- **Disconnected** (red indicator): Connection lost, will retry
- **Connecting** (yellow indicator): Attempting to connect

Connection failures are tracked and the state updates automatically. The UI continues to show cached data while disconnected.

## Development

```bash
# Run with auto-reload
textual run --dev src/hop3_tui/app.py

# Run tests
uv run pytest tests/ -v

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
