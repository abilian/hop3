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
Simply use 'hop3 context add' and authentication happens automatically:

  hop3 context add dev --server ssh://root@my-server.com --default
  hop3 apps  # Auto-authenticates via SSH

Use 'init' only if you want to create a specific admin user with
a custom username, email, and password.

Options:
  --ssh <user@server>    SSH target for the server (required)
  --context <name>       Create a named context for this server
  --username <name>      Admin username (prompted if not provided)
  --email <email>        Admin email (prompted if not provided)
  --server <url>         Server URL (inferred from SSH target if not provided)
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
  --url <url>            Use HTTP API instead of SSH tunnel
  --token <token>        Use a pre-generated API token
  --server <url>         Server URL (for --token)
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

Manage multiple server contexts (similar to kubectl contexts).

Quick start (SSH-based servers):
  hop3 context add dev --server ssh://root@dev.example.com --default
  hop3 context add prod --server ssh://root@prod.example.com --protected
  hop3 apps  # Just works - auto-authenticates via SSH!

Subcommands:
  (bare)            Show current state (active context + default app + source)
  list              List all configured contexts
  show [<name>]     Show details of a context (current by default)
  use <name>        Switch to a different context
  add <name> [opts] Add a new context
  remove <name>     Remove a context
  rename <old> <new>  Rename a context

Add options:
  --server <url>    Server URL (required, e.g., ssh://root@server.com)
  --protected       Mark as protected (extra confirmation for destructive ops)
  --default         Set as the default context
  --token <token>   API token (optional - auto-fetched via SSH if not provided)
  --ssh-user <user> SSH username (default: root)
  --ssh-port <port> SSH port (default: 22)

Use options:
  (default)         Print 'export HOP3_CONTEXT=...' for this shell only
  --global          Set as global default (affects ALL terminals)
  --app <name>      Also set this context's default app (ADR 036 D7/D8)

Examples:
  # Setup for development and production
  hop3 context add dev --server ssh://root@dev.example.com --default
  hop3 context add prod --server ssh://root@prod.example.com --protected

  # Commands use dev by default
  hop3 apps
  hop3 deploy myapp

  # Use production explicitly
  hop3 --context prod apps
  hop3 --context prod deploy myapp

  # Per-project context (ADR 042): from inside a project directory
  cd myproject
  hop3 context use prod        # writes .hop3-local.toml

Context priority (highest to lowest):
  1. --context flag
  2. HOP3_CONTEXT environment variable
  3. .hop3-local.toml [current].context (per-project, ADR 042)
  4. Global config file

Protected contexts require extra confirmation for destructive operations.
SSH-based contexts auto-authenticate - no login needed!
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


SERVER_HELP = """Usage: hop3 server <subcommand> [options]

Manage server bindings — the global registry of Hop3 hosts.

Subcommands:
  list                List configured servers.
  add <name> --url <u> [--token <t>] [--ssh-user <u>] [--ssh-port <p>]
                       [--protected]
                      Register a new server.
  remove <name>       Drop a server.
  show <name>         Display a server's details.
  use <name>          Set the global single-server default.
  use --default-app <app>
                      Set the current server's default app
                      (app-resolution source #8).
  login <name>        Re-authenticate to a server (token rotation).
"""


USE_HELP = """Usage: hop3 use [app]

Set / show / clear the current context's default app (ADR 036 D7/D8).

Examples:
  hop3 use myapp        # Set default app for the current context
  hop3 use              # Show the currently resolved app and its source
  hop3 use --clear      # Clear the default app for the current context
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
    "server": SERVER_HELP,
    "settings": SETTINGS_HELP,
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
