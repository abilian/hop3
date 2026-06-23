# hop3-cli Deep Dive

This document provides detailed internal documentation for the hop3-cli package. For a quick overview, see the [package overview](index.md).

## Architecture Overview

hop3-cli is a thin client that communicates with hop3-server via JSON-RPC. It handles:

1. **Argument Parsing** - Command-line interface
2. **SSH Tunneling** - Secure communication with remote servers
3. **RPC Communication** - JSON-RPC over HTTP
4. **Output Formatting** - Human-readable and JSON output

## Module Structure

```
hop3_cli/
├── main.py              # Entry point, argument parsing, command flow
├── config.py            # Configuration and context management
├── exit_codes.py        # Exit codes (ADR 036 D16)
├── exceptions.py        # CLI exception classes
├── types.py             # Type definitions
├── rpc/
│   ├── client.py        # JSON-RPC client with SSH tunnel support
│   ├── tunnel.py        # SSH tunnel helpers
│   ├── responses.py     # Response handling
│   └── streaming.py     # Streaming (live deploy/log) responses
├── commands/
│   ├── flags.py         # CLI flag parsing
│   ├── destructive.py   # Confirmation prompts
│   ├── help.py          # Help system
│   └── local/           # Commands handled without the server
│       ├── init_cmd.py
│       ├── login_cmd.py
│       ├── settings_cmd.py
│       ├── context_cmd.py
│       └── ...
├── core/                # Resolution, aliases, project context (ADR 036/042)
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
export HOP3_API_URL="http://localhost:8000"
```

### SSH Tunnel Mode

For production servers (secure communication):

```
CLI → SSH Tunnel → localhost:random_port → hop3-server:8000 → response
```

The connection mode is selected by the scheme of the API URL: an `ssh://` (or `ssh+http://`) URL routes RPC through an SSH tunnel, while an `http(s)://` URL connects directly.

```bash
export HOP3_API_URL="ssh://user@hop3.example.com"
```

The tunnel is created by the `Client` (in `rpc/client.py`) using `sshtunnel` (which wraps `paramiko`). On construction, the client parses the API URL and, when the scheme is `ssh`/`ssh+http`, opens an `SSHTunnelForwarder` that binds the remote server port (default 8000) to a local port. RPC then targets `http://localhost:<local_port>/rpc`. The client is a context manager, so the tunnel is closed reliably on exit:

```python
with Client(config=config) as client:
    response = client.rpc("cli", ["app", "list"])
```

## JSON-RPC Protocol

The CLI uses JSON-RPC 2.0 over HTTP, posting to the server's `/rpc` endpoint. The CLI does not map each command to a distinct RPC method. Instead it forwards the raw command tokens under a single `cli` method, and the server parses, dispatches, and executes them. This keeps the client thin: command names, subcommands, and their behavior live entirely server-side.

```json
// Request — `hop3 app list` forwarded as the `cli` method
{
    "jsonrpc": "2.0",
    "method": "cli",
    "params": {
        "cli_args": ["app", "list"],
        "extra_args": {}
    },
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

`extra_args` carries out-of-band values that don't belong in the argv (for example file contents read locally and passed to the server).

### RPC Client

The `Client` (in `rpc/client.py`) takes the loaded `Config`, resolves the API URL, and opens an SSH tunnel when needed. Its `rpc()` method takes the method name (`"cli"`) and the list of command tokens, attaches the bearer token, and parses the JSON-RPC response. If the server returns 401 and an SSH URL is configured, it transparently re-authenticates over SSH and retries once.

```python
class Client:
    def rpc(self, method: str, cli_args: list[str], **extra_args: Any) -> Response:
        """Call a remote method with automatic SSH-based authentication."""
        response = self._do_rpc(method, cli_args, **extra_args)
        if isinstance(response, Error) and response.code == 401:
            if self._can_auto_auth():
                self._auto_authenticate()
                response = self._do_rpc(method, cli_args, **extra_args)
        return response
```

## Command Structure

Commands are organized by type:

### Remote Commands

Most commands are forwarded to the server as the `cli` method, with the command tokens passed verbatim. The app target is always the `--app NAME` flag (ADR 036 D5); when omitted, the CLI resolves it from context (env var, `.hop3-app`, `hop3.toml`, or the context default) and injects it as `--app` before forwarding.

```bash
# These are forwarded to the server as cli(["<tokens>"])
hop3 app list                  # `apps` is a built-in alias for `app list`
hop3 app launch foo            # alias for `app create foo`
hop3 deploy                    # package the current project and deploy
hop3 app logs --app myapp      # show logs for an explicit app
hop3 app logs                  # same, app resolved from context
```

### Local Commands

Some commands run entirely on the client, without an RPC call (see `commands/local/`): `init`, `login`, `settings`, `context`, `server`, `use`, `tunnel`, `aliases`, `completion`, `version`, and bare `auth`.

```bash
# These don't call the server
hop3 init              # Bootstrap a server connection via SSH
hop3 settings show     # Manage local CLI settings (URL, token, SSL)
hop3 version           # Show CLI version
hop3 help              # Show help
```

## Configuration

### Config File

Location: `~/.config/hop3-cli/config.toml` (resolved via `platformdirs`, so the exact path is platform-specific). The file holds the JWT auth token, so it is written atomically and `chmod 0600`.

Connection details are stored as named **contexts**; `current_context` selects the active one. Each context carries its API URL, token, and SSH/TLS settings:

```toml
current_context = "production"

[contexts.production]
api_url = "ssh://root@hop3.example.com"
api_token = "..."
protected = true
ssh_user = "root"
ssh_port = 22
verify_ssl = true
default_app = ""
```

### Config Class

`Config` wraps the parsed TOML `data` dict and resolves values with a fixed priority: environment variable (`HOP3_<KEY>`), then config-file value, then a per-call default, then class defaults. Contexts are read from `data["contexts"]`.

```python
@dataclass
class Config:
    data: dict = field(default_factory=dict)
    config_file: Path | None = None

    def get_api_url(self) -> str | None: ...
    def get_api_token(self) -> str | None: ...
    def get_current_context(self) -> Context | None: ...
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `HOP3_API_URL` | API URL; `ssh://` scheme enables tunneling, `http(s)://` connects directly |
| `HOP3_API_TOKEN` | Authentication (bearer) token |
| `HOP3_CONTEXT` | Select the active context by name |
| `HOP3_APP` | Default app for app-scoped commands |
| `HOP3_DEV_MODE` | When truthy, defaults the API URL to `http://localhost:8000` |
| `HOP3_VERBOSITY` | Default verbosity level (0–3) |
| `HOP3_NO_INPUT` | When `1`, refuse interactive prompts (non-interactive mode) |

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

CLI exceptions derive from `CliError` (in `exceptions.py`):

```python
class CliError(Exception):
    """Base class for CLI exceptions."""

class AuthenticationError(CliError):
    """Raised when authentication fails."""

class DeploymentError(CliError):
    """Raised when a deployment fails."""
```

Exit codes are defined centrally in `exit_codes.py` (ADR 036 D16) rather than as per-exception attributes, so scripts can distinguish failure classes:

```python
class ExitCode:
    SUCCESS = 0
    GENERAL_ERROR = 1
    USAGE_ERROR = 2
    RESOLUTION_ERROR = 3      # app / context / target not found
    AUTH_ERROR = 4
    AUTHZ_ERROR = 5
    CONFLICT_ERROR = 6
    NETWORK_ERROR = 7
    DEPLOYMENT_ERROR = 8
    PLUGIN_ERROR = 9
    CONFIRMATION_DECLINED = 10
    INTERRUPTED = 130         # SIGINT
```

The JSON envelope includes `error.exit_code` so JSON consumers don't have to map error strings.

## Authentication Flow

`hop3 login` (canonical spelling: `hop3 auth login`) is a local handler. Its
password path goes through the server's `auth get-token` primitive:

```
1. User runs: hop3 login   (prompts for username/password)
2. CLI forwards the credentials as cli(["auth", "get-token", user, pass])
3. Server verifies them and returns a JWT token
4. CLI saves the token to the active context (api_token)
5. Subsequent requests include: Authorization: Bearer <token>
```

`hop3 auth get-token <user> --password-file -` exposes that same primitive
directly, for scripts that want to capture a token without saving config.

When the API URL uses an `ssh://` scheme, the CLI can also obtain a token over SSH automatically: on a 401 it runs the SSH bootstrap, fetches a token, saves it to the current context, and retries the request. This is what the local `hop3 init` and `hop3 login` commands rely on.

## Development Notes

### Adding a New Command

Most commands are implemented server-side; the CLI just forwards the tokens via the `cli` RPC method. To add one:

1. Add a `Command` subclass in hop3-server's `commands/` (it defines its own `name` and help text)
2. Nothing is usually needed in the CLI — the new command is reachable as soon as the server exposes it

A purely client-side command (one with local side effects, like `init` or `settings`) is added under `commands/local/` and registered in `LOCAL_COMMANDS_INFO`.

### Testing

```bash
# Run the CLI test suite
pytest -x -p no:randomly src tests

# With coverage
pytest --cov hop3_cli tests src
```

## Future Improvements

- [ ] Interactive mode (REPL)
- [ ] Richer progress reporting for long-running deploys

Multi-server support and shell completion already exist (named contexts and the `completion` command, respectively).
