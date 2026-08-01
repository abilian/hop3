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
├── config.py            # Configuration and context resolution
├── exit_codes.py        # Exit codes (ADR 036 D16)
├── exceptions.py        # CLI exception classes
├── tokens.py            # JWT extraction helpers
├── types.py             # Type definitions
├── rpc/
│   ├── client.py        # JSON-RPC client with SSH tunnel support
│   ├── responses.py     # Response handling
│   └── streaming.py     # Streaming (live deploy/log) responses
├── commands/
│   ├── flags.py         # CLI flag parsing
│   ├── arguments.py     # Argument parsing helpers
│   ├── destructive.py   # Confirmation prompts
│   ├── help.py          # Help system
│   └── local/           # Commands handled without the server (a package)
│       ├── init_cmd.py
│       ├── login_cmd.py
│       ├── settings_cmd.py
│       ├── context_cmd.py
│       ├── tunnel_cmd.py
│       └── ...
├── core/                # Resolution, aliases, credential store, project context
│   ├── credential_store.py  # Per-server bearer-token store (credentials.toml)
│   ├── paths.py             # Config-dir resolution (platformdirs / $HOP3_CONFIG_DIR)
│   └── ...
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

The tunnel is created by the `Client` (in `rpc/client.py`) using an `SshTunnel` (`core/ssh_tunnel.py`), a subprocess `ssh -L` forward that shells out to the system `ssh`. On construction, the client parses the API URL and, when the scheme is `ssh`/`ssh+http`, opens the tunnel binding the remote server port (default 8000) to a local port. RPC then targets `http://localhost:<local_port>/rpc`. The client is a context manager, so the tunnel is closed reliably on exit:

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

Most commands are forwarded to the server as the `cli` method, with the command tokens passed verbatim. The app target is always the `--app NAME` flag (ADR 036 D5); when omitted, the CLI resolves it from where you stand (env var `$HOP3_APP`, a `.hop3-app` file in the CWD or an ancestor, or `hop3.toml`) and injects it as `--app` before forwarding. There is no per-context default app (ADR 042).

```bash
# These are forwarded to the server as cli(["<tokens>"])
hop3 app list                  # `apps` is a built-in alias for `app list`
hop3 app create foo            # create an app from a repository
hop3 deploy                    # package the current project and deploy
hop3 app logs --app myapp      # show logs for an explicit app
hop3 app logs                  # same, app resolved from context
```

### Local Commands

Some commands run entirely on the client, without an RPC call (see `commands/local/`): `init`, `login`, `settings`, `context`, `use`, `tunnel`, `aliases`, `completion`, `version`, and bare `auth`.

```bash
# These don't call the server
hop3 init              # Bootstrap a server connection via SSH
hop3 settings show     # Manage local CLI settings (URL, token, SSL)
hop3 version           # Show CLI version
hop3 help              # Show help
```

## Configuration

Under ADR 042 the CLI's on-disk state is split in two: a **secret-free** `config.toml` for local preferences and **global** contexts, and a **per-server credential store** (`credentials.toml`) for bearer tokens. A *context* — the one target selector — exists at two scopes: a **project** environment in the committed `hop3.toml`, and a **global** named server in `config.toml`. `--context <name>` resolves project-first, then global.

### Config File (`config.toml`)

Location: `~/.config/hop3-cli/config.toml`, resolved via `platformdirs` (so the exact path is platform-specific) and honoring `$HOP3_CONFIG_DIR`. It holds local preferences, the **global** `[contexts.<name>].server` blocks (named servers, address-only) and `[cli].default_context`, plus an optional legacy `[cli].default_server` (and `[cli].current_context`, read-only for one release). It does **not** hold bearer tokens.

```toml
[cli]
default_context = "devel"                       # target for bare project-less commands
# default_server = "ssh://root@host"            # legacy unnamed fallback (lower priority)
# current_context = "devel"                     # legacy, read-only fallback

[contexts.devel]
server = "ssh://root@hop3.example.com"          # a named server — `--context devel` anywhere
```

The file is written atomically (tmpfile + `os.replace`) and `chmod 0600` defensively, even though it carries no secrets.

### Credential Store (`credentials.toml`)

Bearer tokens live in `~/.config/hop3-cli/credentials.toml` (same config dir), keyed by the **canonical** server address:

```toml
[servers."ssh://root@hop3.example.com:22"]
token = "eyJ..."
```

This file is invisible plumbing: `hop3 auth login` / `hop3 init` populate it, deploy/RPC read it, and it is never hand-edited. It is created file-mode `0o600` with parent dir `0o700`, and the store **aborts loudly** rather than ever leaving it group/world-readable (Hop3's "errors are never silent" rule). See `core/credential_store.py`.

### Contexts (the one target selector)

A *context* is a named target, and `--context <name>` is the single selector for every command, app-bound or not. It exists at two scopes: a **project** environment declared under `[contexts.<name>]` in the committed `hop3.toml` (server address, app instance name, domains, env), and a **global** named server in `config.toml` (`[contexts.<name>].server`, address-only) for project-less use. Both are non-secret — the `server` is a literal address, never a token. `--context` resolves project-first, then global; an explicit `--context` that resolves to nothing aborts loud (it never silently retargets). There is no `--server` flag. Contexts are managed with `hop3 context add|use|list|show|remove|rename` (see `commands/local/context_cmd.py`, which operates on the project scope inside a project and the global scope outside one, or with `--global`); the per-checkout project selection is pinned in the gitignored `.hop3-local.toml`.

### Config Class

`Config` wraps the parsed TOML `data` dict and resolves the connection with a fixed priority. The active server is wired per-invocation by `main.py`: an explicit `--context` must resolve project-first then global (`_require_context_server`), else the ambient project context, else the default global context (`[cli].default_context`) / legacy `[cli].default_server` / the sole known server (`_resolve_ambient_server`). The API URL then resolves as: `HOP3_API_URL` env → the resolved context's server (`_active_server`) → `[cli].default_server` → legacy `config.toml` context (read fallback) → dev-mode default. The token comes from the credential store keyed by the active/default server, or from `HOP3_API_TOKEN`.

```python
@dataclass
class Config:
    data: dict = field(default_factory=dict)
    config_file: Path | None = None

    def get_api_url(self) -> str | None: ...
    def get_api_token(self) -> str | None: ...   # reads the credential store
    def get_context_server(self, name: str) -> str | None: ...  # global context -> address
    def get_default_context(self) -> str | None: ...
    def get_default_server(self) -> str | None: ...  # legacy unnamed fallback
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `HOP3_API_URL` | API URL; `ssh://` scheme enables tunneling, `http(s)://` connects directly |
| `HOP3_API_TOKEN` | Authentication (bearer) token |
| `HOP3_CONTEXT` | Select the active context by name |
| `HOP3_CONFIG_DIR` | Override the config directory (config.toml + credentials.toml) |
| `HOP3_DEV_MODE` | When truthy, defaults the API URL to `http://localhost:8000` |

## Output Formatting

The CLI supports multiple output formats:

### Human-Readable (default)

```
$ hop3 app list
NAME        STATE     PORT    UPDATED
myapp       running   8001    2h ago
api         running   8002    1d ago
```

### JSON

```
$ hop3 app list --json
[{"name": "myapp", "state": "running", "port": 8001}, ...]
```

### Quiet

```
$ hop3 app list --quiet
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

`hop3 auth login` (canonical spelling: `hop3 auth login`) is a local handler. Its
password path goes through the server's `auth get-token` primitive:

```
1. User runs: hop3 auth login   (prompts for username/password)
2. CLI forwards the credentials as cli(["auth", "get-token", user, pass])
3. Server verifies them and returns a JWT token
4. CLI saves the token to the per-server credential store (credentials.toml)
   and records the server as the default target
5. Subsequent requests include: Authorization: Bearer <token>
```

`hop3 auth get-token <user> --password-file -` exposes that same primitive
directly, for scripts that want to capture a token without saving config.

`hop3 auth login --ssh <target>` obtains the token over SSH and stores it the same way — in the per-server credential store, keyed by the canonical server address, with the server set as the project-less default. With `--context <name>`, the server is also recorded as a global context in `config.toml` and set as `[cli].default_context` (still secret-free — only the address is written). `config.toml` is never where the token goes. When the API URL uses an `ssh://` scheme, the CLI can also obtain a token over SSH automatically: on a 401 it runs the SSH bootstrap, fetches a token, stores it, and retries the request. This is what the local `hop3 init` and `hop3 auth login` commands rely on.

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

Multi-server support and shell completion already exist (project and global contexts selected by the one `--context` flag, plus the `completion` command, respectively).
