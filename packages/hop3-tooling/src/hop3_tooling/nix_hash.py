# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Compute the vendored-dependency hash a hermetic nix-gen template needs.

The hermetic templates pin their dependency set with a fixed-output derivation,
which requires a hash that can only be learned by building once. Nix's own
workflow is to build with a placeholder and read the reported hash out of the
error; this module automates that cycle so migrating a recipe is one command
instead of a manual edit-build-copy loop.

The parsing and the TOML rewrite are pure functions — the subprocess lives in
the CLI — so the fiddly parts are testable without Nix present.
"""

from __future__ import annotations

import re

# All-A base64 is the conventional "I don't know it yet" hash: it is
# well-formed, so Nix gets far enough to compute the real one and report it.
PLACEHOLDER_HASH = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

# Which [nix] key holds the vendored-dependency hash, per template.
HASH_KEY_BY_TEMPLATE = {
    "python-venv": "pip-deps-hash",
    "php-app": "composer-deps-hash",
    "node-pnpm-install": "node-deps-hash",
    "go-source": "go-vendor-hash",
}

_GOT_HASH = re.compile(r"\bgot:\s*(sha256-[A-Za-z0-9+/=]+)")
_SECTION = re.compile(r"^\s*\[(?P<name>[^\]]+)\]\s*$")


def parse_nix_hash_mismatch(output: str) -> str | None:
    """
    The real hash from a Nix fixed-output mismatch, or None if absent.

    Nix reports the pair as::

        hash mismatch in fixed-output derivation '/nix/store/...':
                 specified: sha256-AAAA...
                    got:    sha256-XmpL...

    Only the ``got:`` value is the answer; ``specified:`` is the placeholder we
    sent in, so matching the wrong one would write the placeholder back.
    """
    match = _GOT_HASH.search(output)
    return match.group(1) if match else None


def set_nix_hash(toml_text: str, key: str, value: str) -> str:
    """
    Set ``key = "value"`` inside the ``[nix]`` table of a hop3.toml.

    Edits the text line-by-line rather than round-tripping through a TOML
    parser, because these recipes carry explanatory comments that a rewrite
    would discard.
    """
    lines = toml_text.splitlines(keepends=True)
    in_nix = False
    nix_header_at = None

    for index, line in enumerate(lines):
        section = _SECTION.match(line)
        if section:
            in_nix = section.group("name") == "nix"
            if in_nix:
                nix_header_at = index
            continue
        if in_nix and re.match(rf"^\s*{re.escape(key)}\s*=", line):
            lines[index] = f'{key} = "{value}"\n'
            return "".join(lines)

    if nix_header_at is None:
        msg = "hop3.toml has no [nix] section — not a nix-gen recipe"
        raise ValueError(msg)

    lines.insert(nix_header_at + 1, f'{key} = "{value}"\n')
    return "".join(lines)


def hash_key_for(template: str) -> str:
    """The [nix] key a template's vendored-dependency hash belongs under."""
    try:
        return HASH_KEY_BY_TEMPLATE[template]
    except KeyError:
        known = ", ".join(sorted(HASH_KEY_BY_TEMPLATE))
        msg = f"template {template!r} vendors no dependencies; expected one of: {known}"
        raise ValueError(msg) from None
