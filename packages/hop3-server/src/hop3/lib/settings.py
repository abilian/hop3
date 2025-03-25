# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Parser and writer for settings files."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from hop3.lib import echo, expand_vars

if TYPE_CHECKING:
    from collections.abc import Mapping


def write_settings(settings_file: str | Path, bag: Mapping, separator="=") -> None:
    """Write out config files."""
    path = Path(settings_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as h:
        for k, v in sorted(bag.items()):
            h.write(f"{k:s}{separator:s}{v}\n")


def parse_settings(
    filename: str | Path,
    env: dict[str, str] | None = None,
) -> dict[str, str]:
    """Parse a settings file and return a dictionary with environment
    variables.

    Input:
    - filename: A string or Path object representing the path to the settings file.
    - env: An optional dictionary of existing environment variables to update. Defaults to None.

    Returns:
    - A dictionary containing the environment variables parsed from the file.
    """
    if env is None:
        env = {}

    path = Path(filename)
    if not path.exists():
        return {}

    settings = path.read_text()

    for line in settings.split("\n"):
        # Ignore comments and newlines
        if line.startswith("#") or len(line.strip()) == 0:
            continue

        try:
            # Parse the line into key and value, expanding any environment variables found
            k, v = (x.strip() for x in line.split("=", 1))
            env[k] = expand_vars(v, env)
        except Exception:
            echo(
                f"Error: malformed setting '{line}', ignoring file.",
                fg="red",
            )
            # TODO: we should probably raise an exception here instead of ignoring the error
            return {}

    return env
