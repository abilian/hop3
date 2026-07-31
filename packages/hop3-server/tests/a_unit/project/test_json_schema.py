# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
The published hop3.toml JSON Schema must match the models it came from.

A schema that has drifted is worse than none: an editor would complete fields
the server rejects, and reject fields it accepts — with the authority of
tooling. Since it is generated, keeping it current is mechanical, so the only
real risk is forgetting to regenerate. This makes that impossible to miss.
"""

from __future__ import annotations

import json
from pathlib import Path

from hop3.project.json_schema import SCHEMA_URL, build_json_schema

REPO = Path(__file__).resolve().parents[5]
COMMITTED = REPO / "schema" / "hop3.toml.schema.json"


def test_the_committed_schema_is_current() -> None:
    """
    Regenerate and compare. Stale means the models moved and this did not.

    Run `uv run scripts/generate-toml-schema.py` to fix.
    """
    expected = json.dumps(build_json_schema(), indent=2, sort_keys=True) + "\n"

    assert COMMITTED.exists(), (
        f"{COMMITTED} is missing — run: uv run scripts/generate-toml-schema.py"
    )
    assert COMMITTED.read_text() == expected, (
        "schema/hop3.toml.schema.json is out of date with the Pydantic models. "
        "Editors would validate recipes against rules the server no longer has. "
        "Run: uv run scripts/generate-toml-schema.py"
    )


def test_toml_facing_names_are_used_not_python_ones() -> None:
    """
    Fields must appear under the names a recipe actually writes.

    The models call it `before_build`; a hop3.toml says `before-build`. Emitting
    the Python names would produce a schema that flags every real recipe as
    wrong and completes fields nobody can use — confidently, and in the editor.
    """
    schema = build_json_schema()
    build_section = schema["$defs"]["BuildSection"]["properties"]

    assert "before-build" in build_section
    assert "static-dir" in build_section
    assert "before_build" not in build_section


def test_unknown_fields_are_rejected_as_the_server_rejects_them() -> None:
    """`extra="forbid"` must survive into the schema, or typos pass in-editor."""
    schema = build_json_schema()

    assert schema["$defs"]["BuildSection"]["additionalProperties"] is False


def test_enums_reach_the_editor() -> None:
    """An editor should offer the valid values, not wait for a failed deploy."""
    schema = build_json_schema()
    login = schema["$defs"]["AdminSection"]["properties"]["login"]

    choices = [entry for entry in login["anyOf"] if "enum" in entry]
    assert choices
    assert set(choices[0]["enum"]) == {"username", "email"}


def test_descriptions_reach_the_editor() -> None:
    """The docstrings already written become hover text, at no extra cost."""
    schema = build_json_schema()
    probe = schema["$defs"]["ProbeSection"]["properties"]["username"]

    assert probe["description"]


def test_the_id_matches_the_published_url() -> None:
    """A recipe's `#:schema <url>` directive must resolve to this document."""
    assert build_json_schema()["$id"] == SCHEMA_URL
