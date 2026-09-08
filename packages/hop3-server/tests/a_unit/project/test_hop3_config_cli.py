# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Tests for `[cli]` in hop3.toml (ADR 042 §Resolution).

`[cli].app` is source #4 of the CLI's app-resolution chain — the CLI reads it
from the committed `hop3.toml` and the deployer ignores it, exactly like
`[contexts.*]`. It was documented in the CLI's README and implemented in
`hop3_cli.core.resolution`, but absent from this schema, which is
`extra="forbid"` — so a project that followed the CLI's own documentation was
rejected at deploy with `Unknown field 'cli'`. These tests pin the two halves
together.
"""

from __future__ import annotations

import pytest

from hop3.project.hop3_config import Hop3Config
from hop3.project.schema import Hop3TomlValidationError

VALID = """
[metadata]
id = "myapp"

[cli]
app = "myapp-prod"

[run]
start = "gunicorn app:app -b 0.0.0.0:$PORT"
"""


def test_cli_app_is_accepted():
    """The regression: this exact file used to fail validation."""
    cfg = Hop3Config.from_str(VALID)

    assert cfg.app_id == "myapp"


def test_the_deployer_ignores_it():
    """`[cli].app` names the app the *CLI* acts on. It must not become the
    deployed app id, or a project that binds to `myapp-prod` locally would
    silently deploy under that name."""
    cfg = Hop3Config.from_str(VALID)

    assert cfg.app_id != "myapp-prod"


def test_an_unknown_key_in_cli_is_still_rejected():
    """Accepting the section is not accepting anything inside it — the
    typo-catching that `extra = "forbid"` exists for still applies."""
    with pytest.raises(Hop3TomlValidationError):
        Hop3Config.from_str('[metadata]\nid = "a"\n[cli]\napp = "a"\nnope = 1\n')


@pytest.mark.parametrize("value", ["", " ", "  myapp  "])
def test_a_padded_or_empty_app_name_is_rejected(value: str):
    """Same rule `[contexts.<name>].app` enforces: omit it to inherit
    `[metadata].id` rather than writing a blank."""
    with pytest.raises(Hop3TomlValidationError):
        Hop3Config.from_str(f'[metadata]\nid = "a"\n[cli]\napp = "{value}"\n')


def test_the_section_is_optional():
    cfg = Hop3Config.from_str('[metadata]\nid = "a"\n')

    assert cfg.app_id == "a"
