# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands handled locally.

These commands are processed by the CLI without requiring an RPC call to the server:
- init: Bootstrap a new server connection via SSH
- login: Authenticate (via SSH or username/password)
- settings: Manage local CLI configuration
- version: Show CLI version
- auth: Show authentication help
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .auth_cmd import handle_auth
from .completion_cmd import handle_completion
from .context_cmd import handle_context
from .init_cmd import handle_init
from .login_cmd import handle_login, handle_login_token
from .settings_cmd import handle_settings, settings_get, settings_set, settings_show
from .ssh_ops import BootstrapError, extract_token, infer_server_url
from .version_cmd import handle_version

if TYPE_CHECKING:
    from hop3_cli.config import Config
    from hop3_cli.ui.rich_printer import RichPrinter

__all__ = [
    "LOCAL_COMMANDS",
    "LOCAL_COMMANDS_INFO",
    "BootstrapError",
    "extract_token",
    "handle_auth",
    "handle_completion",
    "handle_context",
    "handle_init",
    "handle_local_command",
    "handle_login",
    "handle_login_token",
    "handle_settings",
    "handle_version",
    "infer_server_url",
    "is_local_command",
    "settings_get",
    "settings_set",
    "settings_show",
]

# Commands that are handled locally (not sent to server via RPC)
# Format: command_name -> description
LOCAL_COMMANDS_INFO = {
    "completion": "Generate shell completion scripts.",
    "context": "Manage multiple server contexts.",
    "init": "Initialize connection to a Hop3 server via SSH.",
    "login": "Authenticate to a server.",
    "settings": "Manage local CLI settings (server URL, token, SSL).",
    "version": "Show CLI version.",
    "auth": "Authentication commands.",
}

LOCAL_COMMANDS = set(LOCAL_COMMANDS_INFO.keys())


def is_local_command(args: list[str]) -> bool:
    """Check if the command should be handled locally.

    With space-separated commands (ADR 036 D1), most LOCAL_COMMANDS own their
    entire subtree (e.g., `settings show`, `context use prod`, `completion bash`
    are all handled locally). The exception is `auth`: `hop3 auth` bare shows
    help locally, but `hop3 auth login` / `auth whoami` / etc. go to the server.
    """
    if not args:
        return False

    command = args[0]

    # Handle --version and -V flags as local command
    if command in {"--version", "-V"}:
        return True

    if command not in LOCAL_COMMANDS:
        return False

    # Special case: `auth <verb>` is a server command (ADR 036 D9: `login`,
    # `logout`, `whoami` are top-level aliases; canonical lives in the server's
    # `auth` namespace). Bare `hop3 auth` and `hop3 auth --help` stay local.
    return not (command == "auth" and len(args) > 1 and not args[1].startswith("-"))


def handle_local_command(args: list[str], config: Config, printer: RichPrinter) -> bool:
    """Handle a local command.

    Returns:
        True if the command was handled, False if it should be sent to server
    """
    if not args:
        return False

    command = args[0]
    cmd_args = args[1:]

    if command == "completion":
        handle_completion(cmd_args, config, printer)
        return True
    if command == "context":
        handle_context(cmd_args, config, printer)
        return True
    if command == "init":
        handle_init(cmd_args, config, printer)
        return True
    if command == "login":
        handle_login(cmd_args, config, printer)
        return True
    if command == "settings":
        handle_settings(cmd_args, config, printer)
        return True
    if command in {"version", "--version", "-V"}:
        handle_version(cmd_args, config, printer)
        return True
    if command == "auth":
        # handle_auth returns False if command should go to server
        return handle_auth(cmd_args, config, printer)

    return False
