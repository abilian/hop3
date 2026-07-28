# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
`[build].ignore` is the canonical deploy-ignore mechanism (ADR 046 §5).

The `.hop3ignore` sidecar and the `[build].ignore-file` pointer are removed:
patterns live inline in `hop3.toml`. A config still using `ignore-file` must
fail loud (unknown field) rather than be silently ignored.
"""

from __future__ import annotations

import pytest
import tomllib

from hop3.project.hop3_config import Hop3Config
from hop3.project.schema import Hop3TomlValidationError, validate_hop3_toml


def test_build_ignore_list_is_accepted():
    toml = '[build]\nignore = ["*.log", "node_modules/", "dist/"]\n'
    validate_hop3_toml(tomllib.loads(toml))  # must not raise


def test_build_ignore_is_readable_from_the_section():
    """
    The CLI reads [build].ignore straight off the section and owns the
    behaviour (hop3-cli's test_generate_archive); the server exposed a duplicate
    accessor that nothing called, which is now gone.
    """
    cfg = Hop3Config.from_str('[build]\nignore = ["*.log", "tmp/"]\n')
    assert cfg.build["ignore"] == ["*.log", "tmp/"]


def test_no_ignore_leaves_the_key_absent():
    assert "ignore" not in Hop3Config.from_str('[metadata]\nid = "x"\n').build


def test_ignore_file_pointer_is_rejected():
    # The legacy [build].ignore-file is gone — extra=forbid rejects it loudly.
    with pytest.raises(Hop3TomlValidationError):
        validate_hop3_toml(tomllib.loads('[build]\nignore-file = ".hop3ignore"\n'))
