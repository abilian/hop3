# hop3-cli

Command-line interface for interacting with Hop3 servers.

## Overview

hop3-cli is a thin client that communicates with hop3-server via JSON-RPC over HTTP or SSH tunneling. It provides a familiar Heroku-like CLI experience for deploying and managing applications.

## Features

- **Application management** - Deploy, start, stop, restart, and scale applications
- **Environment variables** - Securely manage app configuration
- **Log streaming** - View real-time application logs
- **Addon management** - Provision and manage backing services (PostgreSQL, Redis, MySQL)
- **SSH tunneling** - Secure communication with remote servers
- **Multiple output formats** - Human-readable, JSON, or quiet mode

## Installation

### From PyPI (end users)

```bash
pip install hop3-cli
```

### For development

```bash
# From workspace root
cd packages/hop3-cli
uv pip install -e ".[dev]"
```

## Quick Start

```bash
# Configure server connection
export HOP3_SERVER_URL="https://hop3.example.com"
# Or use SSH tunneling
export HOP3_SERVER="user@hop3.example.com"

# Authenticate
hop3 auth login

# Deploy an application
cd my-app
hop3 deploy

# View logs
hop3 logs my-app

# List applications
hop3 apps
```

## Configuration

Configuration can be set via environment variables or config file (`~/.config/hop3/config.toml`).

| Variable | Description | Default |
|----------|-------------|---------|
| `HOP3_SERVER_URL` | Server URL (HTTP mode) | - |
| `HOP3_SERVER` | Server hostname (SSH mode) | - |
| `HOP3_AUTH_TOKEN` | Authentication token | - |
| `HOP3_CONFIG_DIR` | Config directory | `~/.config/hop3` |

## Architecture

```
hop3-cli/
├── src/hop3_cli/
│   ├── main.py          # Entry point, argument parsing
│   ├── config.py        # Configuration management
│   ├── tunnel.py        # SSH tunnel management
│   ├── rpc/
│   │   └── client.py    # JSON-RPC client
│   ├── commands/
│   │   ├── local.py     # Local commands (init, config)
│   │   └── help.py      # Help system
│   └── ui/
│       ├── console.py   # Output formatting
│       └── prompts.py   # Interactive prompts
└── tests/
```

**Communication flow:**
```
User → CLI → [SSH Tunnel] → HTTP → hop3-server → JSON-RPC response → CLI → User
```

## Development

### Running tests

```bash
# From package directory
uv run pytest tests/ -v

# With coverage
uv run pytest tests/ --cov=hop3_cli
```

### Code quality

```bash
# Lint
uv run ruff check src/

# Format
uv run ruff format src/

# Type check
uv run pyright src/
```

## Documentation

- **User Guide**: [Main documentation](../../docs/src/guide.md)
- **CLI Reference**: [Command reference](../../docs/src/cli-reference.md)
- **System Architecture**: [Architecture overview](../../docs/src/dev/architecture.md)
- **Package Internals**: [Deep-dive documentation](./docs/internals.md)

## Related Packages

- [hop3-server](../hop3-server/) - The server that hop3-cli communicates with
- [hop3-tui](../hop3-tui/) - Alternative terminal UI interface

## License

Apache-2.0 - Copyright (c) 2024-2025, Abilian SAS
