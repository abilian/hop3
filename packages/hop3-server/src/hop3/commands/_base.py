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

from typing import ClassVar

from hop3.lib.registry import lookup

from ._response import text


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

    def call(self, *args, **kwargs):
        return self.get_help()

    def get_help(self):
        """Default help for namespace-bare invocations (ADR 036 M4.3).

        Produces the same D11-structured output as `hop help <ns>`:
        `hop <ns> — <summary>`, USAGE (inferred), EXAMPLES (from docstring),
        DESCRIPTION (body), SUBCOMMANDS, and "Part of:" line for nested
        namespaces. The shared renderer lives in `_help_render.py` so this
        stays in sync with `HelpCmd._detailed_help`.
        """
        # Lazy import to avoid an import cycle with `help.py`.
        from ._help_render import (  # noqa: PLC0415
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

    def subcommands(self):
        return []
