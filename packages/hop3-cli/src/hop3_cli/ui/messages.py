# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""User-facing messages for setup and error states."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hop3_cli.config import Config


def _say(text: str) -> None:
    """Each message says why a command cannot run: stderr, like any error."""
    print(text, file=sys.stderr)


def show_unauthenticated_message(config: Config) -> None:
    """
    Say which server has no credential, and how to get one for *that* server.

    It used to advertise `hop3 init` (which the CLI's own help says you no
    longer need) and claim the token is saved to config.toml (it has not been
    since tokens moved to the secret-free credential store). Worse, it named no
    server: when the target comes from `HOP3_API_URL`, `hop3 login` stores a
    credential under whatever address the login resolves — which is not
    necessarily the one the next command will use.
    """
    from hop3_cli.config import ENV_CONTEXT_NAME  # ruff:ignore[import-outside-top-level]

    target = config.get_api_url()
    context = config.get_current_context_name()

    if target:
        where = f"{target}  (context {context!r})" if context else target
        _say(f"No credential for {where}.\n")
    else:
        _say("Authentication required.\n")

    if context == ENV_CONTEXT_NAME:
        # `hop3 login` would store a token for whatever address it resolves,
        # while every command keeps going to the exported URL. Say the thing
        # that actually fixes it.
        _say("That target comes from your environment, so logging in elsewhere")
        _say("will not change where commands go. Either:\n")
        _say("  export HOP3_API_TOKEN=<token>       # a token for that server")
        _say("  unset HOP3_API_URL                  # or use your stored context")
        return

    _say("Sign in — your SSH access to the server is the credential:\n")
    _say("  hop3 login root@your-server.com\n")
    _say("Without SSH access, `hop3 login` prompts for a username and password.")
    _say("For automation, export HOP3_API_TOKEN.")
