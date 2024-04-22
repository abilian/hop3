# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

"""Parser and writer for settings files."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from click import secho as echo

from hop3.util.templating import expand_vars


def write_settings(settings_file: str | Path, bag: Mapping, separator="=") -> None:
    """Write out config files."""
    path = Path(settings_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as h:
        for k, v in sorted(bag.items()):
            h.write(f"{k:s}{separator:s}{v}\n")


def parse_settings(
    filename: str | Path,
    env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Parse a settings file and returns a dict with environment variables."""
    if env is None:
        env = {}

    path = Path(filename)
    if not path.exists():
        return {}

    settings = path.read_text()

    for line in settings.split("\n"):
        # ignore comments and newlines
        if line.startswith("#") or len(line.strip()) == 0:
            continue

        try:
            k, v = (x.strip() for x in line.split("=", 1))
            env[k] = expand_vars(v, env)
        except Exception:
            echo(
                f"Error: malformed setting '{line}', ignoring file.",
                fg="red",
            )
            return {}

    return env
