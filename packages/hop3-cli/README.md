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

# List applications
hop3 apps

# View application logs
hop3 logs myapp

# Set environment variables
hop3 config:set myapp KEY=value
```

## Configuration

Configuration can be set via environment variables or config file (`~/.config/hop3-cli/config.toml`).

| Variable | Description | Default |
|----------|-------------|---------|
| `HOP3_API_URL` | Server URL (HTTP or SSH) | - |
| `HOP3_API_TOKEN` | Authentication token | - |
| `HOP3_DEV_MODE` | Enable development mode | `false` |

## Architecture

```
hop3-cli/
├── src/hop3_cli/
│   ├── main.py           # Entry point, argument parsing
│   ├── config.py         # Configuration management
│   ├── rpc/
│   │   └── client.py     # JSON-RPC client with SSH tunnel
│   ├── commands/
│   │   ├── local.py      # Local commands (init, login, settings)
│   │   ├── flags.py      # CLI flag parsing
│   │   └── destructive.py # Confirmation prompts
│   └── ui/
│       └── rich_printer.py # Output formatting
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

- [User Guide](../../docs/src/guide.md)
- [CLI Reference](../../docs/src/cli-reference.md)

## Related Packages

- [hop3-server](../hop3-server/) - The server that hop3-cli communicates with
- [hop3-tui](../hop3-tui/) - Alternative terminal UI interface

## License

Apache-2.0 - Copyright (c) 2024-2026, Abilian SAS
