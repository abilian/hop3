# hop3-tui

Terminal User Interface for Hop3 PaaS.

## Features

- Dashboard overview with system stats and app summary
- Application list with filtering and quick actions
- Application detail view with start/stop/restart controls
- Real-time log streaming
- Chat/command interface for interactive operations
- System status monitoring

## Installation

```bash
# Install with uv (from workspace root)
uv sync

# Or install directly
pip install hop3-tui
```

## Usage

```bash
# Run the TUI
hop3-tui

# Or run as a module
python -m hop3_tui
```

## Keyboard Shortcuts

### Global

| Key | Action |
|-----|--------|
| `?` | Help |
| `q` | Quit |
| `d` | Dashboard |
| `a` | Apps |
| `s` | System |
| `c` | Chat |

### Navigation

| Key | Action |
|-----|--------|
| `j` / `↓` | Move down |
| `k` / `↑` | Move up |
| `Enter` | Select |
| `Escape` | Back |

## Development

```bash
# Install dev dependencies
uv sync --group dev

# Run in development mode with auto-reload
textual run --dev src/hop3_tui/app.py
```

## License

Apache-2.0
