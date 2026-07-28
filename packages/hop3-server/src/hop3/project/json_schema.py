# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Emit the hop3.toml JSON Schema, for editors.

Derived from the same Pydantic models the server validates with, so the two
cannot disagree — a hand-written copy would drift the moment a field changed,
and a schema that lies about the fields is worse than none.

What this buys, over the server-side validation that already exists: the same
rules, hours earlier. An editor with a TOML language server (Taplo — VS Code's
"Even Better TOML", Neovim, Helix; JetBrains has its own) completes field names,
offers enum values, shows each field's description on hover, and underlines a
typo as it is typed, instead of after a deploy fails.

What it does NOT carry: the cross-field validators. "[admin] needs a username or
an email", "[probe].login must name an identifier the recipe declares" — those
are Python and stay server-side. The editor checks shape; the server keeps
meaning. Nor does it help with a field that is valid but unimplemented, which is
a different failure (see tests/a_unit/project/test_no_dead_config.py).
"""

from __future__ import annotations

from typing import Any

from hop3.project.schema import Hop3TomlSchema

#: Where the generated schema is published, so a recipe can point at it with
#: Taplo's `#:schema <url>` directive.
SCHEMA_URL = "https://hop3.cloud/schema/hop3.toml.json"


def build_json_schema() -> dict[str, Any]:
    """
    Return the hop3.toml JSON Schema as a plain dict.

    ``by_alias=True`` is essential: the models name fields in Python style
    (``before_build``), while a recipe writes the alias (``before-build``).
    Emitting the Python names would produce a schema that rejects every real
    hop3.toml and completes fields nobody can use.
    """
    schema = Hop3TomlSchema.model_json_schema(by_alias=True)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = SCHEMA_URL
    schema["title"] = "hop3.toml"
    schema["description"] = (
        "Configuration for a Hop3 application. Generated from the server's "
        "own validation models; cross-field rules are enforced at deploy time."
    )
    return schema
