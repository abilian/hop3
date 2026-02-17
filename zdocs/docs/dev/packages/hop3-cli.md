# hop3-cli Deep Dive

This document provides detailed internal documentation for the hop3-cli package. For a quick overview, see the [package README](../README.md).

## Architecture Overview

hop3-cli is a thin client that communicates with hop3-server via JSON-RPC. It handles:

1. **Argument Parsing** - Command-line interface
2. **SSH Tunneling** - Secure communication with remote servers
3. **RPC Communication** - JSON-RPC over HTTP
4. **Output Formatting** - Human-readable and JSON output

## Module Structure

```
hop3_cli/
├── main.py              # Entry point, argument parsing
├── config.py            # Configuration management
├── tunnel.py            # SSH tunnel management
├── types.py             # Type definitions
├── rpc/
│   └── client.py        # JSON-RPC client
├── commands/
│   ├── local.py         # Local commands (init, config)
│   ├── help.py          # Help system
│   ├── flags.py         # CLI flag parsing
│   └── destructive.py   # Confirmation prompts
└── ui/
    ├── console.py       # Output formatting
    ├── rich_printer.py  # Rich terminal output
    └── prompts.py       # Interactive prompts
```

## Communication Model

### Direct HTTP Mode

For servers exposed directly (development or internal networks):

```
CLI → HTTP → hop3-server:8000 → JSON-RPC response → CLI
```

Configuration:
```bash
export HOP3_SERVER_URL="http://localhost:8000"
```

### SSH Tunnel Mode

For production servers (secure communication):

```
CLI → SSH Tunnel → localhost:random_port → hop3-server:8000 → response
```

Configuration:
```bash
export HOP3_SERVER="user@hop3.example.com"
```

The tunnel is created using `sshtunnel` and `paramiko`:

```python
def create_tunnel(host: str, ssh_key: Path | None = None) -> SSHTunnelForwarder:
    """Create SSH tunnel to hop3 server."""
    tunnel = SSHTunnelForwarder(
        host,
        ssh_pkey=str(ssh_key) if ssh_key else None,
        remote_bind_address=("127.0.0.1", 8000),
    )
    tunnel.start()
    return tunnel
```

## JSON-RPC Protocol

The CLI uses JSON-RPC 2.0 for communication:

```json
// Request
{
    "jsonrpc": "2.0",
    "method": "apps.list",
    "params": {},
    "id": 1
}

// Response
{
    "jsonrpc": "2.0",
    "result": [
        {"name": "myapp", "state": "running", "port": 8001}
    ],
    "id": 1
}
```

### RPC Client

```python
class RPCClient:
    def __init__(self, base_url: str, token: str | None = None):
        self.base_url = base_url
        self.token = token

    def call(self, method: str, **params) -> Any:
        """Make an RPC call."""
        response = requests.post(
            f"{self.base_url}/rpc",
            json={
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
                "id": self._next_id(),
            },
            headers=self._auth_headers(),
        )
        return self._handle_response(response)
```

## Command Structure

Commands are organized by type:

### Remote Commands

Most commands are forwarded to the server:

```python
# These call server RPC methods
hop3 apps              # → apps.list
hop3 apps:create foo   # → apps.create(name="foo")
hop3 deploy            # → apps.deploy(...)
hop3 logs myapp        # → apps.logs(name="myapp")
```

### Local Commands

Some commands run entirely on the client:

```python
# These don't call the server
hop3 init              # Create hop3.toml
hop3 config            # Manage local configuration
hop3 help              # Show help
```

## Configuration

### Config File

Location: `~/.config/hop3/config.toml`

```toml
[server]
url = "https://hop3.example.com"
# or
host = "user@hop3.example.com"

[auth]
token = "..."

[output]
format = "human"  # human, json, quiet
color = true
```

### Config Class

```python
@dataclass
class Config:
    server_url: str | None = None
    server_host: str | None = None
    auth_token: str | None = None
    output_format: str = "human"

    @classmethod
    def load(cls) -> "Config":
        """Load config from file and environment."""
        ...
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `HOP3_SERVER_URL` | Direct HTTP URL |
| `HOP3_SERVER` | SSH host (enables tunneling) |
| `HOP3_AUTH_TOKEN` | Authentication token |
| `HOP3_CONFIG_DIR` | Config directory |
| `HOP3_OUTPUT_FORMAT` | Output format |

## Output Formatting

The CLI supports multiple output formats:

### Human-Readable (default)

```
$ hop3 apps
NAME        STATE     PORT    UPDATED
myapp       running   8001    2h ago
api         running   8002    1d ago
```

### JSON

```
$ hop3 apps --json
[{"name": "myapp", "state": "running", "port": 8001}, ...]
```

### Quiet

```
$ hop3 apps --quiet
myapp
api
```

## Error Handling

The CLI handles errors at multiple levels:

1. **Connection errors** - Network/SSH failures
2. **Authentication errors** - Invalid or expired tokens
3. **RPC errors** - Server-side command failures
4. **User errors** - Invalid input

```python
class CLIError(Exception):
    """Base class for CLI errors."""
    exit_code: int = 1

class AuthenticationError(CLIError):
    """Authentication failed."""
    exit_code: int = 2

class ConnectionError(CLIError):
    """Could not connect to server."""
    exit_code: int = 3
```

## Authentication Flow

```
1. User runs: hop3 auth login
2. CLI prompts for credentials
3. CLI sends: auth.login(username, password)
4. Server returns: JWT token
5. CLI stores token in config file
6. Subsequent requests include: Authorization: Bearer <token>
```

## Development Notes

### Adding a New Command

1. Add RPC method to hop3-server
2. Add CLI command in `commands/`
3. Update help text

### Testing

```bash
# Unit tests
pytest tests/unit/

# Integration tests (requires server)
pytest tests/integration/
```

## Future Improvements

- [ ] Command auto-completion
- [ ] Interactive mode (REPL)
- [ ] Multi-server support
- [ ] Config profiles
