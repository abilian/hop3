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
  --ssh <user@server>    Use SSH-based authentication
  --token <token>        Use a pre-generated API token
  --server <url>         Server URL (for --token, prompted if not configured)
  --username <name>      Username (for password auth, prompted if not provided)

Examples:
  # URL with embedded token (easiest for local development)
  hop3-server admin:create admin admin@example.com  # Get token
  hop3 login "http://localhost:8000?token=eyJ..."

  # SSH-based login (for remote servers)
  hop3 login --ssh root@my-server.com

  # Password-based login (server must be configured)
  hop3 login

Note: For first-time setup (creating a new admin user), use:
  hop3 init --ssh root@my-server.com
""")
