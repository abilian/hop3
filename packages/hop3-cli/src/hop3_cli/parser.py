from __future__ import annotations

import argparse

from hop3_cli.cli_metadata import ARG_GROUPS, CLI_CONFIG


class ParserBuildError(Exception):
    """Raised when there's an error building the parser."""


def _resolve_arg_groups(arguments_config):
    """Resolves argument group references (like [*ARG_GROUPS['context']])."""
    resolved_args = []
    if not arguments_config:
        return resolved_args

    for arg_def in arguments_config:
        match arg_def:
            case str() as group_name:
                if group_name in ARG_GROUPS:
                    # Recursively resolve potential nested groups within the referenced group
                    resolved_args.extend(_resolve_arg_groups(ARG_GROUPS[group_name]))
                else:
                    # Handle error: referenced group not found
                    raise ParserBuildError(
                        f"Argument group '{group_name}' not found in ARG_GROUPS."
                    )

            case dict():
                resolved_args.append(arg_def)
            case _:
                # Handle error: invalid item in arguments list
                raise ParserBuildError(
                    f"Invalid item in arguments definition: {arg_def}"
                )

    return resolved_args


def build_parser_from_config(config, parser=None):
    """
    Recursively builds an argparse parser from a declarative configuration dict.

    Args:
        config: The dictionary defining the parser or subparser.
        parser: The argparse parser (or subparser) to add definitions to.
                If None, a new top-level ArgumentParser is created.

    Returns:
        The configured argparse parser.
    """
    if parser is None:
        # Create the top-level parser
        parser = argparse.ArgumentParser(
            prog=config.get("prog"),
            description=config.get("description"),
            epilog=config.get("epilog"),
            # Allow arguments to be abbreviated if unique
            allow_abbrev=False,
            # Use raw description formatting if needed later
            # formatter_class=argparse.RawDescriptionHelpFormatter
            exit_on_error=False,
        )

    # Add arguments defined at this level
    resolved_arguments = _resolve_arg_groups(config.get("arguments"))
    for arg_config in resolved_arguments:
        arg_config = arg_config.copy()  # Avoid modifying the original config
        flags = arg_config.pop("flags", [])
        name = arg_config.pop("name", None)

        # Special handling for version action to pass the version string
        if arg_config.get("action") == "version":
            version_str = arg_config.pop("version", None)
            if version_str:
                arg_config["version"] = version_str

        # Handle type conversion (only basic types for now)
        arg_type = arg_config.get("type")
        if arg_type == int:
            arg_config["type"] = int
        elif arg_type == float:
            arg_config["type"] = float
        # Add more types if needed

        if flags:  # It's an optional argument/option
            # argparse expects positional args first in add_argument call
            parser.add_argument(*flags, **arg_config)
        elif name:  # It's a positional argument
            parser.add_argument(name, **arg_config)
        else:
            raise ParserBuildError(
                f"Warning: Argument definition missing 'name' or 'flags': {arg_config}"
            )

    # Add subparsers if defined
    if "subcommands" in config:
        subparser_opts = config.get("subparser_options", {})
        # Make sure dest is set if subparsers are required
        if subparser_opts.get("required") and "dest" not in subparser_opts:
            raise ParserBuildError(
                f"Warning: Subparsers are required but 'dest' is missing in subparser_options for {config.get('name', 'root')}"
            )
            # Default 'dest' if missing but required? Decide on behavior.
            # subparser_opts.setdefault("dest", "subcommand") # Example default

        subparsers = parser.add_subparsers(**subparser_opts)

        for sub_config in config["subcommands"]:
            sub_config = sub_config.copy()
            sub_name = sub_config.get("name")
            if not sub_name:
                raise ParserBuildError(
                    f"Warning: Subcommand definition missing 'name': {sub_config}"
                )

            # Extract help and description for add_parser
            sub_help = sub_config.get("help")
            sub_desc = sub_config.get("description")
            aliases = sub_config.get("aliases", [])

            # Create the subparser instance
            sub_parser = subparsers.add_parser(
                sub_name,
                help=sub_help,
                description=sub_desc or sub_help,  # Use help as description if missing
                aliases=aliases,
            )

            # Recursively build the subparser
            build_parser_from_config(sub_config, sub_parser)

    return parser


def create_parser():
    """Creates the main Hop3 CLI parser from the declarative definition."""
    return build_parser_from_config(CLI_CONFIG)
