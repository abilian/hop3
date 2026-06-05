# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Help text for local commands."""

from __future__ import annotations


def print_init_help():
    """Print help for the init command."""
    print("""Usage: hop3 init --ssh <user@server> [options]

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
""")


def print_settings_help():
    """Print help for the settings command."""
    print("""Usage: hop3 settings <subcommand> [args]

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
""")


def print_login_help():
    """Print help for the login command."""
    print("""Usage: hop3 login [options]

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
""")


def print_context_help():
    """Print help for the context command."""
    print("""Usage: hop3 context <subcommand> [args]

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
""")
