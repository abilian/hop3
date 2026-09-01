# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""The offline command list must name commands that actually exist.

The list the CLI falls back on before it has ever reached a server is
hand-maintained, and it rotted once already: it still named the pre-ADR-036
`config:*` spellings, and a bad reformat had flattened `"addons create"` into a
bare `"create"`. Shell completion offered those. This pins every entry to a
real command.
"""

from __future__ import annotations

import pytest
from hop3_cli.commands.local import LOCAL_COMMANDS_INFO
from hop3_cli.commands.local.completion_cmd import FALLBACK_COMMANDS


@pytest.fixture(scope="module")
def server_command_names() -> set[str]:
    """Top-level names from the server's registry (dev workspace only)."""
    rpc = pytest.importorskip(
        "hop3.server.controllers.rpc",
        reason="hop3-server is not installed alongside the CLI",
    )
    return {name[0] for name, cmd in rpc.commands.items() if not cmd.hidden}


def test_every_fallback_name_is_real(server_command_names: set[str]) -> None:
    known = server_command_names | set(LOCAL_COMMANDS_INFO)
    unknown = sorted(set(FALLBACK_COMMANDS) - known)
    assert not unknown, f"fallback names that are not commands: {unknown}"


def test_every_top_level_server_command_is_offered(
    server_command_names: set[str],
) -> None:
    """A new top-level command must show up in offline completion too."""
    missing = sorted(server_command_names - set(FALLBACK_COMMANDS))
    assert not missing, f"top-level commands missing from the fallback list: {missing}"


def test_the_list_holds_no_fragments() -> None:
    """Every entry is one token: subcommands come from the server-filled cache."""
    assert [name for name in FALLBACK_COMMANDS if " " in name] == []
