# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Help text for local (client-side) commands.

This module is the single source of truth for the long-form help of every
command handled by the CLI itself (never sent to the server). Each command's
handler prints the matching constant for its ``--help`` output, and
``hop3 help --all -v`` aggregates them all (see
``hop3_cli.commands.help.append_local_commands_full_help``).
"""

from __future__ import annotations

INIT_HELP = """Usage: hop3 init --ssh <user@server> [options]

Bootstrap a new Hop3 server with a custom admin user.

NOTE: For most cases, you don't need this command anymore!
Authenticate once over SSH, then declare your deploy environment:

  hop3 login --ssh root@my-server.com
  hop3 context add dev --server ssh://root@my-server.com --app myapp
  hop3 apps  # uses the resolved context

Use 'init' only if you want to create a specific admin user with
a custom username, email, and password.

Options:
  --ssh <user@server>    SSH target for the server (required)
  --context <name>       Suggest a hop3.toml context name for this server
  --username <name>      Admin username (prompted if not provided)
  --email <email>        Admin email (prompted if not provided)
  --url <url>            Server URL (inferred from SSH target if not provided)
  --password-stdin       Read password from stdin
  -y, --yes              Skip confirmation prompts

Examples:
  # Create admin with custom credentials
  hop3 init --ssh root@my-server.com --context prod \\
    --username myadmin --email admin@company.com
"""


SETTINGS_HELP = """Usage: hop3 settings <subcommand> [args]

Manage local CLI settings.

Subcommands:
  show              Show current settings
  set <key> <value> Set a settings value
  get <key>         Get a settings value

Keys:
  server (api_url)  Server URL (e.g., https://my-server.com)
  token (api_token) API authentication token
  ssl_cert          Path to trusted certificate file (for self-signed certs)
  verify_ssl        Verify SSL certificates (true/false, default: true)

Examples:
  hop3 settings show
  hop3 settings set server https://my-server.com
  hop3 settings set token eyJhbGciOiJI...
  hop3 settings set ssl_cert ~/server.crt  # Trust a specific certificate
  hop3 settings set verify_ssl false       # Disable SSL verification (less secure)
  hop3 settings get server
"""


LOGIN_HELP = """Usage: hop3 login [options]

Authenticate to a Hop3 server.

SSH-based login (recommended):
  hop3 login --ssh root@my-server.com

  SSH access IS authentication - no username or password needed.
  The server automatically creates or selects an admin user.

Other authentication methods:
  <url>?token=<token>    URL with embedded token (for local dev)
  --token <token>        Use a pre-generated token
  (default)              Username/password authentication

Options:
  --ssh <user@server>    SSH-based authentication (recommended)
  --username <name>      Specific user (optional, defaults to auto-select)
  --url <url>            Server URL (HTTP API; pair with --token for token auth)
  --token <token>        Use a pre-generated API token
  -d, -dd, -ddd          Debug output (more d's = more verbose)

Examples:
  # SSH-based login (simplest - just works)
  hop3 login --ssh root@my-server.com

  # URL with embedded token (for local development)
  hop3 login "http://localhost:8000?token=eyJ..."

  # Password-based login (for users without SSH access)
  hop3 login

Note: With contexts, login is often not needed - auto-auth happens
automatically when you run commands. See 'hop3 context --help'.
"""


CONTEXT_HELP = """Usage: hop3 context <subcommand> [args]

Manage deploy environments (dev / staging / prod) for this project. A context
is a [contexts.<name>] block in the committed hop3.toml: a non-secret bundle of
server address + app instance + domains + env (ADR 042).

Quick start:
  hop3 context add prod --server ssh://root@prod.example.com --app myapp
  hop3 context add dev  --server ssh://root@dev.example.com  --app myapp-dev
  hop3 context use dev        # pin this checkout to dev
  hop3 deploy                 # deploys the selected environment

Subcommands:
  (bare)              Show the selected context + what's declared
  list                List the [contexts.*] in the nearest hop3.toml
  show [<name>]       Show one context (the selected one by default)
  add <name> [opts]   Add a [contexts.<name>] block to hop3.toml
  remove <name>       Remove a [contexts.<name>] block
  rename <old> <new>  Rename a context
  use <name>          Pin a context for THIS checkout (.hop3-local.toml)

Add options (write hop3.toml — no secrets):
  --server <addr>   Target server address (required), e.g. ssh://root@host
  --app <name>      App instance name (optional; inherits [metadata].id)
  --domain <host>   Hostname (repeatable)
  --env KEY=VALUE   Non-secret env override (repeatable)

Which file each verb touches:
  add / remove / rename  ->  hop3.toml         (committed, shared — commit it)
  use                    ->  .hop3-local.toml  (per-checkout, gitignored)

Context selection (highest to lowest):
  1. --context flag
  2. HOP3_CONTEXT environment variable
  3. .hop3-local.toml [local].context
  4. single-context fallback (when hop3.toml declares exactly one)

Secrets never go in hop3.toml: the server is a literal address, and per-env
secrets are set server-side with `hop3 env set`.
"""


ALIASES_HELP = """Usage: hop3 aliases

List all effective aliases (ADR 036 D9).

Shows each alias's source token, expansion, and origin (built-in, plugin,
or user). User aliases come from `~/.config/hop3-cli/config.toml` under
the `[aliases]` section:

    [aliases]
    pg = "addon postgres"
    ll = "app list"

Aliases must not collide with built-in or plugin aliases (D9: no shadowing).
Colliding user aliases are reported at the bottom and skipped at resolution.
"""


COMPLETION_HELP = """Usage: hop3 completion <shell|option>

Generate shell completion scripts.

Shells:
  bash      Generate bash completion script
  zsh       Generate zsh completion script
  fish      Generate fish completion script

Options:
  --refresh   Fetch current commands from server and update cache
  --status    Show cache status (location, age, command count)

Installation:

  Bash (current session):
    eval "$(hop3 completion bash)"

  Bash (permanent):
    hop3 completion bash > /etc/bash_completion.d/hop3
    # Or for user-specific:
    hop3 completion bash >> ~/.bashrc

  Zsh (current session):
    eval "$(hop3 completion zsh)"

  Zsh (permanent):
    hop3 completion zsh > ~/.zsh/completions/_hop3
    # Make sure ~/.zsh/completions is in your fpath

  Fish:
    hop3 completion fish > ~/.config/fish/completions/hop3.fish

Keeping Completions Updated:

  The completion scripts read from a local cache file that can be
  updated from the server. No need to regenerate scripts after refresh:

    hop3 completion --refresh    # Fetch latest commands from server
    hop3 completion --status     # Check cache status

Examples:
  hop3 completion bash      # Output bash completion script
  hop3 completion --refresh # Update command cache from server
  hop3 completion --status  # Show cache info
"""


USE_HELP = """Usage: hop3 use [app]

Pin / show / clear the app for the current directory (ADR 042).

Writes a `.hop3-app` file in the current directory — the app then resolves
from the CWD (app-resolution source #4). There is no per-context default app.

Examples:
  hop3 use myapp        # Pin myapp for this directory (writes .hop3-app)
  hop3 use              # Show the currently resolved app and its source
  hop3 use --clear      # Remove the .hop3-app pin for this directory
"""


TUNNEL_HELP = """Usage: hop3 tunnel <addon-name> [--port <localport>]

Open a local SSH tunnel to a remote addon and print a ready-to-paste local
connection URL. Forwards a local port to the addon's port on the server over
the configured SSH connection, then holds the tunnel open until you press
Ctrl-C. The addon's type is resolved from its name (no --type needed).

Options:
  --port <localport>    Local port to bind (default: the addon's own port).
                        Use this if the default port is already in use.

Examples:
  hop3 tunnel mydb              # postgresql://...@127.0.0.1:5432/mydb
  hop3 tunnel mydb --port 6543  # bind a different local port
  hop3 tunnel mycache           # redis://...@127.0.0.1:6379/0
"""


# Maps each local command name to its long-form help text. Used by
# `hop3 help --all -v` to aggregate the full client-side help. `auth` is
# intentionally absent: its real subcommands (auth login/whoami/...) are
# server-side and already documented in the server portion of the document.
LOCAL_COMMAND_HELP: dict[str, str] = {
    "aliases": ALIASES_HELP,
    "completion": COMPLETION_HELP,
    "context": CONTEXT_HELP,
    "init": INIT_HELP,
    "login": LOGIN_HELP,
    "settings": SETTINGS_HELP,
    "tunnel": TUNNEL_HELP,
    "use": USE_HELP,
}


def print_init_help() -> None:
    """Print help for the init command."""
    print(INIT_HELP)


def print_settings_help() -> None:
    """Print help for the settings command."""
    print(SETTINGS_HELP)


def print_login_help() -> None:
    """Print help for the login command."""
    print(LOGIN_HELP)


def print_context_help() -> None:
    """Print help for the context command."""
    print(CONTEXT_HELP)
