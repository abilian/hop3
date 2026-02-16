# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Help text for local commands."""

from __future__ import annotations


def print_init_help():
    """Print help for the init command."""
    print("""Usage: hop3 init --ssh <user@server> [options]

Bootstrap a new Hop3 server connection by creating an admin user.

Options:
  --ssh <user@server>    SSH target for the server (required)
  --username <name>      Admin username (prompted if not provided)
  --email <email>        Admin email (prompted if not provided)
  --server <url>         Server URL (inferred from SSH target if not provided)
  --password-stdin       Read password from stdin
  -y, --yes              Skip confirmation prompts

Examples:
  # Interactive setup
  hop3 init --ssh root@my-server.com

  # Non-interactive setup
  echo "secretpass" | hop3 init --ssh root@my-server.com \\
    --username admin --email admin@example.com --password-stdin -y
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

Authentication methods:
  <url>?token=<token>    URL with embedded token (easiest for local dev)
  --ssh <user@server>    SSH-based authentication (for remote servers)
  --token <token>        Use a pre-generated token (with --server)
  (default)              Username/password authentication

Options:
  --ssh <user@server>    Use SSH-based authentication (uses SSH tunnel for all commands)
  --url <url>            With --ssh: use HTTP API at this URL instead of SSH tunnel
  --token <token>        Use a pre-generated API token
  --server <url>         Server URL (for --token, prompted if not configured)
  --username <name>      Username (prompted if not provided)
  -d, -dd, -ddd          Debug output (more d's = more verbose)

Examples:
  # SSH-based login (recommended for remote servers)
  # All subsequent commands will use SSH tunnel
  hop3 login --ssh root@my-server.com

  # SSH-based login with HTTP API for subsequent commands
  hop3 login --ssh root@my-server.com --url https://my-server.com

  # Show debug info
  hop3 login --ssh root@my-server.com -d

  # URL with embedded token (easiest for local development)
  hop3 login "http://localhost:8000?token=eyJ..."

  # Password-based login (server must be configured)
  hop3 login

Note: For first-time setup (creating a new admin user), use:
  hop3 init --ssh root@my-server.com
""")


def print_context_help():
    """Print help for the context command."""
    print("""Usage: hop3 context <subcommand> [args]

Manage multiple server contexts (similar to kubectl contexts).

Subcommands:
  list              List all configured contexts
  current           Show the current context and its source
  use <name>        Switch to a different context (see options below)
  add <name> [opts] Add a new context
  remove <name>     Remove a context

Use options (safe by default):
  (default)         Print 'export HOP3_CONTEXT=...' for this shell only
  --local           Write to .hop3-context file in current directory
  --global          Set as global default (affects ALL terminals - use with caution)

Add options:
  --server <url>    Server URL (required)
  --token <token>   API authentication token
  --protected       Mark as protected (requires confirmation for destructive ops)
  --ssh-user <user> SSH username (default: root)
  --ssh-port <port> SSH port (default: 22)

Examples:
  # List all contexts
  hop3 context list

  # Add a staging context
  hop3 context add staging --server ssh://root@staging.example.com

  # Add a protected production context
  hop3 context add production --server ssh://root@prod.example.com --protected

  # Switch to production (prints export command - safest)
  hop3 context use production

  # Switch to production for this project directory
  hop3 context use production --local

  # Switch to production globally (all terminals - dangerous!)
  hop3 context use production --global

  # Show current context and where it's set
  hop3 context current

  # Use a context for a single command
  hop3 --context production apps

Context priority (highest to lowest):
  1. --context flag
  2. HOP3_CONTEXT environment variable
  3. .hop3-context file in current directory
  4. Global config file (~/.config/hop3-cli/config.toml)

Protected contexts require extra confirmation before destructive operations
like 'app:destroy' or 'services:destroy'.
""")
