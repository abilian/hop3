# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Help text for local (client-side) commands.

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

  hop3 login root@my-server.com
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


LOGIN_HELP = """Usage: hop3 login [<user>@<host>] [options]

Authenticate this CLI to a Hop3 server:

  hop3 login root@my-server.com

Your SSH access to the server IS the credential, so there is no password to
type: this asks the server for an API token over SSH and stores it, creating
or selecting an admin user as needed.

SSH is the bootstrap, not the everyday route. The server is asked for its own
public address, and when it has one — an admin domain with a certificate this
machine trusts — that is what every later command talks to over HTTPS. The SSH
target is kept only to renew the token when it expires. A server with no admin
domain has no HTTPS endpoint, so commands tunnel over SSH as root instead, and
the login says so.

The web dashboard holds a SEPARATE credential — a browser session, not this
token — and signing in here does not sign you in there:

  hop3 login --browser                   # a link for the current server
  hop3 login --browser root@my-server.com

That is not the alternative to the form above. It travels over SSH too, and it
is not a login: it prints a one-time URL for you to open, good for 5 minutes
and one use.

Without SSH access, both surfaces fall back to username/password: `hop3 login`
here, the dashboard's own form in the browser.

Options:
  <user>@<host>          Mint a CLI token over SSH (a bare host means root@)
  --browser [<target>]   Print a one-time link for the web dashboard
  --context <name>       Name this server, and make it the default target
  --username <name>      Specific user (optional, defaults to auto-select)
  --url <url>            Server URL (HTTP API; pair with --token for token auth)
  --token <token>        Use a pre-generated API token
  -d, -dd, -ddd          Debug output (more d's = more verbose)

Examples:
  # Authenticate the CLI (simplest - just works)
  hop3 login root@my-server.com

  # Get into the web dashboard without a password
  hop3 login --browser

  # Name the server, so `--context prod` selects it from anywhere
  hop3 login --context prod root@prod.example.com

  # Sign in to it again later: the context records its SSH route
  hop3 login --context prod

  # URL with embedded token (for local development)
  hop3 login "http://localhost:8000?token=eyJ..."

  # Password-based login (for users without SSH access)
  hop3 login

Lost the admin password? You don't need it to get in, and you don't need to
reset it on the server:
  hop3 login root@my-server.com
  hop3 user set-password admin --stdin

When HTTPS is what's broken — an expired certificate, a proxy that is down —
`--via-ssh` sends one command through the SSH route instead:
  hop3 apps --via-ssh

Note: `--ssh <target>` is the old spelling of the positional form and `--web`
of `--browser`; both still work.
"""


CONTEXT_HELP = """Usage: hop3 context <subcommand> [args]

A context is a named target — the one selector for every command. Select one with
`--context <name>` (or `-c`); it resolves project-first, then global. Two scopes:

  Global   ~/.config/hop3-cli/config.toml — just a named server, so commands like
           `hop3 apps --context prod` work with no project. Defined outside a
           project (or with --global).
  Project  the committed hop3.toml — a deploy environment: server + app + domains
           + env. Defined inside a project.

Quick start (project-less — manage your servers by name):
  hop3 login --context prod --ssh root@prod.example.com   # name + authenticate
  hop3 apps --context prod                                # target it anywhere

Quick start (in a project — per-environment deploys):
  hop3 context add prod --server ssh://root@prod.example.com --app myapp
  hop3 context use prod        # pin this checkout to prod
  hop3 deploy                  # deploys the selected environment

Subcommands (operate on the current scope; --global forces global):
  (bare)              Show contexts at the current scope
  list                List contexts (global outside a project, else project)
  show [<name>]       Show one context
  add <name> [opts]   Define a context (global = named server; project = full)
  remove <name>       Remove a context
  rename <old> <new>  Rename a project context
  use <name>          Pin a PROJECT context for THIS checkout (.hop3-local.toml)
  use --global <name> Make a GLOBAL context the default target (config.toml)

Add options:
  --server <addr>   Target server address (required), e.g. ssh://root@host
  --global, -g      Define a global (named-server) context in config.toml
  --app <name>      App instance name        (project context only)
  --domain <host>   Hostname (repeatable)    (project context only)
  --env KEY=VALUE   Non-secret env override  (project context only)

Context selection (highest to lowest):
  1. --context flag
  2. HOP3_CONTEXT environment variable
  3. .hop3-local.toml [local].context  (per-checkout, project)
  4. single-context fallback (project) / default global context (project-less)

No secrets anywhere: a context's server is a literal address; the token lives in
the credential store; per-env secrets are set server-side with `hop3 env set`.
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


SCAFFOLD_HELP = """Usage: hop3 scaffold [--force]

Write a starter hop3.toml for the project in this directory.

Reads the working tree and writes one file; nothing is sent to a server, and
no server needs to exist yet. The app id comes from the directory name, and
the toolchain Hop3 would detect is reported (but not written: Hop3 detects it
again at deploy, so a hard-coded value is only something to get wrong later).

The generated file starts with a `#:schema` line, so an editor with a TOML
language server ("Even Better TOML" in VS Code, or Taplo over LSP) completes
field names, offers valid values, and flags typos as you type.

Options:
  -f, --force   Replace an existing hop3.toml. Refused by default: it is
                hand-edited and may be the only record of how the app deploys.

Next step:
  hop3 deploy
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
