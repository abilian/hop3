# Copyright (c) 2023-2025, Abilian SAS

"""
Command Docstring Convention
============================

When writing CLI commands, follow this docstring convention:

- **First Line**: A brief one-line summary (shown in ``hop --help`` overview)
- **Blank Line**: Separate the summary from detailed help
- **Detailed Help**: Usage instructions, examples, and detailed description (shown when asking for specific command help)

Example:

.. code-block:: python

    class MyCmd(Command):
        '''Brief one-line summary of what this command does.

        This is the detailed help that includes usage instructions,
        examples, and more detailed explanations.

        Usage: hop mycommand <arg1> <arg2>

        Examples:
            hop mycommand foo bar
            hop mycommand --option value
        '''
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from hop3.lib.registry import lookup

from ._response import text

if TYPE_CHECKING:
    from collections.abc import Callable


class Command:
    # Command name as a tuple of tokens (ADR 036 D1/D18). For example:
    #   `hop3 env set` has name = ("env", "set")
    #   `hop3 addon postgres diagnose` has name = ("addon", "postgres", "diagnose")
    # A one-token name (e.g., ("deploy",)) is a top-level command.
    # An empty tuple is the default for the base class only.
    name: ClassVar[tuple[str, ...]] = ()

    # Command aliases: alternative names (also as tuples). Server-side aliases are
    # a legacy mechanism; per ADR 036 D9 the canonical alias table is client-side.
    # Kept here for backward compatibility with a small number of server-registered
    # aliases.
    aliases: ClassVar[list[tuple[str, ...]]] = []

    # Authentication metadata (default: requires auth, doesn't need username)
    requires_auth: ClassVar[bool] = True
    pass_username: ClassVar[bool] = False
    # Destructive action metadata (default: not destructive)
    # Set to True for commands that delete/destroy data (requires confirmation)
    destructive: ClassVar[bool] = False
    # Hidden commands are not shown in help output (for internal/technical commands)
    hidden: ClassVar[bool] = False

    # Each concrete command supplies `call` with its own typed, readable
    # signature (the named params it needs, plus `*args`/`**kwargs` to absorb any
    # extra marshaled tokens); namespace parents inherit it from
    # `NamespaceCommand`. The dispatcher (server/controllers/rpc.py) invokes it
    # with the RPC layer's marshaled positional/keyword args, so the base pins
    # only the shape it relies on: a callable returning the response-item list.
    # Declaring `call` as a Callable attribute rather than a fixed method
    # signature is deliberate — commands genuinely do not form an LSP hierarchy
    # over `call` (each takes different args), and this lets every command's real
    # signature stand without a spurious `[override]` conflict or a suppression.
    call: Callable[..., list[dict]]

    def get_help(self) -> list[dict]:
        """
        Default help for namespace-bare invocations (ADR 036 M4.3).

        Produces the same D11-structured output as `hop help <ns>`:
        `hop <ns> — <summary>`, USAGE (inferred), EXAMPLES (from docstring),
        DESCRIPTION (body), SUBCOMMANDS, and "Part of:" line for nested
        namespaces. The shared renderer lives in `_help_render.py` so this
        stays in sync with `HelpCmd._detailed_help`.
        """
        # Lazy import to avoid an import cycle with `help.py`.
        from ._help_render import (  # ruff:ignore[import-outside-top-level]
            parse_docstring_sections,
            render_detailed_help,
            render_subcommands,
            short_help,
        )

        namespace = self.name
        display_name = " ".join(namespace) if namespace else ""
        sections = parse_docstring_sections(self.__doc__)

        # If the docstring doesn't supply a Usage block, synthesize one for
        # namespace commands.
        if not sections["usage"]:
            sections["usage"] = [f"hop {display_name} <subcommand>"]

        output = render_detailed_help(display_name, sections)
        commands = lookup(Command)
        output.extend(render_subcommands(commands, namespace, short_help))

        # "Part of:" line for nested namespaces (e.g., `hop addon postgres`).
        if len(namespace) > 1:
            output.append(f"Part of: hop {namespace[0]} namespace.")

        return [text("\n".join(output))]


class NamespaceCommand(Command):
    """
    A namespace parent (e.g. `hop3 app`, `hop3 addon`): it groups subcommands but
    has no action of its own, so invoking it bare prints the namespace help.
    """

    def call(self, *args: str, **kwargs: object) -> list[dict]:
        return self.get_help()
