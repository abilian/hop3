# hop3-tui

Terminal User Interface for Hop3 PaaS.

A modern, keyboard-driven terminal interface for managing your Hop3 applications, built with [Textual](https://textual.textualize.io/).

## Features

- **Dashboard overview** - System stats, app summary, recent activity, quick actions
- **Applications management** - List, filter, start/stop/restart apps with keyboard shortcuts
- **App detail view** - Detailed information with action buttons and logs preview
- **Environment variables** - View, add, edit, delete env vars with sensitive value hiding
- **Real-time log streaming** - Filter logs, pause/resume, auto-scroll
- **Chat/command interface** - Interactive command line with tab completion
- **System monitoring** - CPU, memory, disk usage and service status

## Installation

```bash
# Install from workspace root
uv sync

# Or install the package directly
pip install hop3-tui
```

## Quick Start

```bash
# Set your server URL (or use config file)
export HOP3_SERVER_URL="https://hop3.example.com"
export HOP3_TOKEN="your-api-token"

# Run the TUI
hop3-tui

# Or run as a module
python -m hop3_tui
```

## Configuration

Configuration can be provided via environment variables or a TOML config file.

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `HOP3_SERVER_URL` or `HOP3_URL` | Server URL | `http://localhost:5000` |
| `HOP3_AUTH_TOKEN` or `HOP3_TOKEN` | API authentication token | (none) |
| `HOP3_TUI_THEME` | Color theme (`dark` or `light`) | `dark` |
| `HOP3_TUI_REFRESH` | Auto-refresh interval in seconds | `5` |

### Config File

The TUI looks for configuration in these locations (in order):

1. `./hop3-tui.toml` (current directory)
2. `./.hop3-tui.toml` (hidden file in current directory)
3. `~/.config/hop3/tui.toml`
4. `~/.hop3/tui.toml`

Example configuration file:

```toml
# hop3-tui.toml

[server]
url = "https://hop3.example.com"
token = "your-api-token"

[display]
theme = "dark"          # dark or light
refresh_interval = 5    # seconds
show_clock = true

[behavior]
auto_refresh = true
confirm_destructive = true
```

## Keyboard Shortcuts

### Global Navigation

| Key | Action |
|-----|--------|
| `d` | Go to Dashboard |
| `a` | Go to Apps list |
| `s` | Go to System status |
| `c` | Go to Chat/command interface |
| `?` | Show help |
| `q` | Quit |

### List Navigation

| Key | Action |
|-----|--------|
| `j` / `Down` | Move down |
| `k` / `Up` | Move up |
| `Enter` | Select / View details |
| `Escape` | Go back |
| `/` | Focus filter input |
| `R` | Refresh |

### Apps Screen

| Key | Action |
|-----|--------|
| `s` | Start selected app |
| `S` | Stop selected app |
| `r` | Restart selected app |
| `n` | New app |

### App Detail Screen

| Key | Action |
|-----|--------|
| `l` | View logs |
| `e` | View environment variables |
| `s` | Stop app |
| `r` | Restart app |
| `R` | Refresh |

### Logs Screen

| Key | Action |
|-----|--------|
| `Space` | Pause/resume streaming |
| `g` | Scroll to top |
| `G` | Scroll to bottom |
| `/` | Filter logs |
| `d` | Download logs |

## Chat Commands

The chat interface supports these commands with **Tab completion**:

| Command | Description |
|---------|-------------|
| `apps` | List all applications |
| `app <name>` | Show app details |
| `start <name>` | Start application |
| `stop <name>` | Stop application |
| `restart <name>` | Restart application |
| `logs <name>` | View recent logs |
| `env <name>` | Show environment variables |
| `status` | Show system status |
| `clear` | Clear chat history |
| `help` or `?` | Show help |
| `deploy <name>` | Deploy application |
| `backup <name>` | Create backup |
| `restore <id>` | Restore backup |

**Tab Completion**: Press `Tab` while typing to auto-complete commands and app names.

## Screens Overview

### Dashboard

```
+----------------------------------+----------------------------------+
| APPLICATIONS                     | SYSTEM STATUS                    |
| Running: 5                       | CPU:    ████░░░░░░ 42%           |
| Stopped: 2                       | Memory: ██████░░░░ 63%           |
| Failed:  1                       | Disk:   ████████░░ 81%           |
+----------------------------------+----------------------------------+
| RECENT ACTIVITY                  | QUICK ACTIONS                    |
| No recent activity               | [d] Deploy new app               |
|                                  | [b] Create backup                |
|                                  | [l] View system logs             |
+----------------------------------+----------------------------------+
```

### Apps List

```
+----------------------------------------------------------------------+
| Applications                                         Filter: [______] |
+----------------------------------------------------------------------+
| NAME           STATUS     PORT    RUNTIME      UPDATED               |
| > myapp        RUNNING    8000    uwsgi        2h ago                |
|   api-server   RUNNING    8001    uwsgi        1d ago                |
|   worker       STOPPED    -       uwsgi        3d ago                |
+----------------------------------------------------------------------+
```

### Chat Interface

```
+----------------------------------------------------------------------+
| Hop3 Command Interface                                                |
+----------------------------------------------------------------------+
| Welcome to Hop3 Command Interface                                     |
| Type a command or ? for help                                          |
|                                                                       |
| > apps                                                                |
|                                                                       |
| Applications                                                          |
| -----------                                                           |
| * myapp        RUNNING  :8000                                         |
| * api-server   RUNNING  :8001                                         |
| o worker       STOPPED                                                |
|                                                                       |
| > _                                                                   |
+----------------------------------------------------------------------+
```

## Development

### Setup

```bash
# Clone and install dependencies
git clone <repository>
cd hop3/packages/hop3-tui
uv sync

# Install dev dependencies
uv sync --group dev
```

### Running in Development

```bash
# Run with auto-reload on file changes
textual run --dev src/hop3_tui/app.py

# Or run normally
python -m hop3_tui
```

### Running Tests

```bash
# Run all tests
uv run pytest tests/ -v

# Run with coverage
uv run pytest tests/ --cov=hop3_tui --cov-report=term-missing

# Run specific test file
uv run pytest tests/test_screens.py -v
```

### Project Structure

```
packages/hop3-tui/
├── pyproject.toml
├── README.md
├── src/
│   └── hop3_tui/
│       ├── __init__.py
│       ├── __main__.py           # Entry point
│       ├── app.py                # Main Hop3TUI class
│       ├── config.py             # Configuration handling
│       ├── api/
│       │   ├── __init__.py
│       │   ├── client.py         # JSON-RPC API client
│       │   └── models.py         # Pydantic data models
│       ├── screens/
│       │   ├── __init__.py
│       │   ├── dashboard.py      # Main dashboard
│       │   ├── apps.py           # Apps list
│       │   ├── app_detail.py     # App detail view
│       │   ├── env_vars.py       # Environment variables
│       │   ├── logs.py           # Log viewer
│       │   ├── system.py         # System status
│       │   └── chat.py           # Chat interface (with tab completion)
│       ├── widgets/
│       │   ├── __init__.py
│       │   ├── status_badge.py   # Status indicator
│       │   ├── status_panel.py   # System status panel
│       │   └── confirmation.py   # Confirmation dialog
│       └── styles/
│           └── base.tcss         # Global styles
└── tests/
    ├── __init__.py
    ├── test_app.py               # App tests
    ├── test_client.py            # API client tests
    ├── test_config.py            # Configuration tests
    ├── test_models.py            # Model tests
    ├── test_screens.py           # Screen tests
    └── test_widgets.py           # Widget tests
```

## API Integration

The TUI communicates with the Hop3 server via JSON-RPC over HTTP. The API client supports:

- Authentication via bearer tokens
- Async operations with httpx
- Automatic retry on connection errors
- Request ID tracking

## Documentation

- **User Guide**: [Main documentation](../../docs/src/guide.md)
- **System Architecture**: [Architecture overview](../../docs/src/dev/architecture.md)
- **Package Internals**: [Deep-dive documentation](./docs/internals.md)

## Related Packages

- [hop3-server](../hop3-server/) - The server that hop3-tui communicates with
- [hop3-cli](../hop3-cli/) - Alternative command-line interface

## License

Apache-2.0 - Copyright (c) 2024-2025, Abilian SAS
