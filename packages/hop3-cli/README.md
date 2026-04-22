# hop3-cli

Command-line interface for interacting with Hop3 servers.

## Overview

hop3-cli is a thin client that communicates with hop3-server via JSON-RPC over HTTP or SSH tunneling. It provides a familiar Heroku-like CLI experience for deploying and managing applications.

## Features

- **Application management**: Deploy, start, stop, restart, and scale applications
- **Environment variables**: Securely manage app configuration
- **Log streaming**: View real-time application logs
- **Addon management**: Provision and manage backing services (PostgreSQL, Redis, MySQL)
- **SSH tunneling**: Secure communication with remote servers
- **Multiple output formats**: Human-readable, JSON, or quiet mode

## Installation

```bash
pip install hop3-cli
```

## Quick Start

```bash
# Initialize connection to a Hop3 server
hop3 init user@hop3.example.com

# Or configure via environment
export HOP3_API_URL="ssh://user@hop3.example.com"

# List applications (no app target needed)
hop3 apps

# Bind a default app for this shell/context (sticky)
hop3 use myapp

# From here on, app-scoped commands resolve myapp automatically:
hop3 logs
hop3 config set KEY=value
hop3 restart
```

## App Resolution

Commands that act on a single app (`logs`, `restart`, `config set`, `run`, …) no longer take the app name as a positional argument. Instead the CLI resolves it from a layered chain, walking sources until one supplies a value (ADR 036 D7):

1. `--app <name>` / `-a <name>` — explicit flag, wins over everything.
2. `$HOP3_APP` — environment variable for the current shell.
3. `.hop3-app` — one-line file in CWD or any ancestor up to `$HOME`. Drop it in a project repo and `hop3` from inside picks up the right app.
4. `hop3.toml [cli].app` — same search path as `.hop3-app`, lower priority.
5. Active context's `default_app` — set via `hop3 use <app>`.

Use `hop3 --why <command>` to print the full trace and see which source won.

```bash
# Explicit (always works):
hop3 logs --app myapp
hop3 config set --app myapp KEY=value

# Sticky app for the context:
hop3 use myapp
hop3 logs

# Per-shell:
export HOP3_APP=myapp

# Per-directory:
echo myapp > .hop3-app

# Debug:
hop3 --why logs
```

See [CLI Reference: App Resolution](../../docs/src/reference/cli.md#app-resolution) for the full specification.

## Configuration

Configuration can be set via environment variables or config file (`~/.config/hop3-cli/config.toml`).

| Variable | Description | Default |
|----------|-------------|---------|
| `HOP3_API_URL` | Server URL (HTTP or SSH) | - |
| `HOP3_API_TOKEN` | Authentication token | - |
| `HOP3_APP` | Default app for app-scoped commands | - |
| `HOP3_CONTEXT` | Active context name | - |
| `HOP3_DEV_MODE` | Enable development mode | `false` |

## Architecture

```
hop3-cli/
├── src/hop3_cli/
│   ├── main.py              # Entry point, argument parsing
│   ├── config.py            # Configuration management
│   ├── core/
│   │   └── resolution.py    # App resolution chain (ADR 036 D7)
│   ├── rpc/
│   │   └── client.py        # JSON-RPC client with SSH tunnel
│   ├── commands/
│   │   ├── local.py         # Local commands (init, login, settings)
│   │   ├── flags.py         # CLI flag parsing (--app, --why, --json, -y, …)
│   │   └── destructive.py   # Confirmation prompts
│   └── ui/
│       └── rich_printer.py  # Output formatting
└── tests/
```

## Development

```bash
# Run tests
uv run pytest tests/ -v

# Lint and format
uv run ruff check src/
uv run ruff format src/
```

## Documentation

- [User Guide](../../docs/src/guides/user-guide.md)
- [CLI Reference](../../docs/src/reference/cli.md)
- [Cheat Sheet](../../docs/src/guides/cheat-sheet.md)
- [CLI Migration Guide](../../docs/src/guides/cli-migration.md)

## Related Packages

- [hop3-server](../hop3-server/) - The server that hop3-cli communicates with
- [hop3-tui](../hop3-tui/) - Alternative terminal UI interface

## License

Apache-2.0 - Copyright (c) 2024-2026, Abilian SAS
