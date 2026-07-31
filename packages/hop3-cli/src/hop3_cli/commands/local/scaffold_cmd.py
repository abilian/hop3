# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
`hop3 scaffold` — write a starter hop3.toml for the project in this directory.

Local by design: it reads the working tree and writes one file. Nothing is sent
to a server, and no server needs to exist yet.

The generated file is deliberately small. Hop3 is convention-over-configuration
— a Python project with a requirements.txt needs no [build] section at all — so
scaffolding a full template would mostly produce settings whose defaults were
already right, and which then rot. What it does emit is the part that is genuinely
per-project (the app's id) plus the `#:schema` line, so the author's editor can
complete and validate every field they add afterwards.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hop3_cli.config import Config
    from hop3_cli.ui.rich_printer import RichPrinter

#: Published alongside the docs site; a TOML language server (Taplo — VS Code's
#: "Even Better TOML", Neovim, Helix) reads this directive and validates the
#: file as it is typed.
SCHEMA_URL = "https://hop3.cloud/schema/hop3.toml.json"

CONFIG_NAME = "hop3.toml"

#: Marker file -> the toolchain Hop3 would detect anyway. Used only to tell the
#: author what was recognised; it is NOT written into the file, because a
#: hard-coded toolchain is a thing to get wrong later when the project changes.
_MARKERS: tuple[tuple[str, str], ...] = (
    ("requirements.txt", "python"),
    ("pyproject.toml", "python"),
    ("package.json", "node"),
    ("composer.json", "php"),
    ("go.mod", "go"),
    ("Cargo.toml", "rust"),
    ("Gemfile", "ruby"),
    ("pom.xml", "java"),
    ("index.html", "static"),
)


def detect_toolchain(directory: Path) -> str | None:
    """Which toolchain Hop3 will detect here, or None if nothing is recognised."""
    for marker, toolchain in _MARKERS:
        if (directory / marker).exists():
            return toolchain
    return None


def suggest_app_id(directory: Path) -> str:
    """
    A valid app id derived from the directory name.

    App names are lowercase and may hold letters, digits and hyphens, so an
    id that fails validation must never be the thing we hand someone as a
    starting point.
    """
    raw = directory.resolve().name.lower()
    cleaned = re.sub(r"[^a-z0-9-]+", "-", raw).strip("-")
    return cleaned or "my-app"


def render(app_id: str, toolchain: str | None) -> str:
    """The starter file's contents."""
    detected = (
        f"# Detected a {toolchain} project — Hop3 works that out at deploy time,\n"
        f"# so there is nothing to declare here unless you need to override it.\n"
        if toolchain
        else "# No known project markers here (requirements.txt, package.json, ...).\n"
        "# Hop3 detects the toolchain at deploy time; declare [build].toolchain\n"
        "# if it guesses wrong.\n"
    )
    return f"""#:schema {SCHEMA_URL}
# hop3.toml — see https://hop3.cloud/reference/config/
#
# The schema line above lets your editor complete field names, offer valid
# values, and flag typos as you type (needs a TOML language server, e.g.
# "Even Better TOML" in VS Code).

[metadata]
id = "{app_id}"

{detected}
# Hostname(s) this app answers on. Remove to let the server assign one.
# [domains]
# list = ["{app_id}.example.com"]

# Backing services, provisioned and wired into the app's environment.
# [[addons]]
# type = "postgres"
"""


def handle_scaffold(args: list[str], config: Config, printer: RichPrinter) -> None:
    """
    Write a starter hop3.toml into the current directory.

    Refuses to overwrite an existing one: a hop3.toml is hand-edited and often
    the only record of how an app is deployed, so clobbering it silently would
    be unrecoverable. `--force` is the explicit way to say otherwise.
    """
    # Before ANY side effect: asking for help must never write a file. This
    # command creates one in the working directory, so a missed --help means an
    # unwanted hop3.toml wherever the operator happened to be standing.
    if "--help" in args or "-h" in args:
        _show_help()
        return

    force = "--force" in args or "-f" in args
    directory = Path.cwd()
    target = directory / CONFIG_NAME

    if target.exists() and not force:
        print(
            f"Error: {CONFIG_NAME} already exists here. Refusing to overwrite it "
            f"— it is hand-edited and may be the only record of how this app "
            f"deploys. Use --force if you really mean to replace it.",
            file=sys.stderr,
        )
        return

    app_id = suggest_app_id(directory)
    toolchain = detect_toolchain(directory)
    target.write_text(render(app_id, toolchain))

    print(f"Wrote {CONFIG_NAME}")
    print(f"  app id:    {app_id}")
    print(f"  detected:  {toolchain or 'nothing recognised — Hop3 will still try'}")
    print("  next:      hop3 deploy")


def _show_help() -> None:
    from .help_text import SCAFFOLD_HELP  # ruff:ignore[import-outside-top-level]

    print(SCAFFOLD_HELP)
