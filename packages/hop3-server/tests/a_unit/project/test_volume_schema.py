# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Schema + parsing for [[volumes]] declarative persistence (ADR 046 §2)."""

from __future__ import annotations

import pytest
import tomllib

from hop3.project.hop3_config import Hop3Config
from hop3.project.schema import Hop3TomlValidationError, validate_hop3_toml


def test_volume_parses_with_defaults():
    cfg = Hop3Config.from_str(
        '[[volumes]]\nname = "uploads"\ntarget = "data/uploads"\n'
    )
    assert cfg.volumes == [
        {
            "name": "uploads",
            "target": "data/uploads",
            "type": "persist",
            "size": None,
            "mode": None,
            "backup": None,
        }
    ]


def test_no_volume_section_is_empty_list():
    assert Hop3Config.from_str('[metadata]\nid = "x"\n').volumes == []


def test_volume_backup_include_false_parses():
    cfg = Hop3Config.from_str(
        '[[volumes]]\nname = "store"\ntarget = "storage"\n'
        "[volumes.backup]\ninclude = false\n"
    )
    assert cfg.volumes[0]["backup"] == {"include": False}


def test_valid_volumes_pass():
    toml = (
        '[[volumes]]\nname = "uploads"\ntarget = "data/uploads"\nmode = "0700"\n'
        '[[volumes]]\nname = "cache"\ntarget = "var/cache"\ntype = "persist"\n'
        '[[volumes]]\nname = "store"\ntarget = "storage"\n[volumes.backup]\ninclude = true\n'
        # size is valid only on a tmpfs volume:
        '[[volumes]]\nname = "scratch"\ntarget = "tmp"\ntype = "tmpfs"\nsize = "256M"\n'
    )
    validate_hop3_toml(tomllib.loads(toml))  # must not raise


@pytest.mark.parametrize(
    "toml",
    [
        '[[volumes]]\nname = "x"',  # missing target
        '[[volumes]]\ntarget = "data"',  # missing name
        '[[volumes]]\nname = "x"\ntarget = "data"\ntype = "weird"',  # bad type
        '[[volumes]]\nname = "bad name"\ntarget = "data"',  # bad name
        '[[volumes]]\nname = "x"\ntarget = "/etc/passwd"',  # absolute target
        '[[volumes]]\nname = "x"\ntarget = "../escape"',  # traversal
        '[[volumes]]\nname = "x"\ntarget = "data"\nbogus = 1',  # unknown field
        '[[volumes]]\nname = "x"\ntarget = "data"\nmode = "nope"',  # bad octal mode
        '[[volumes]]\nname = "x"\ntarget = "data"\nsize = "256M"',  # size on persist
        # duplicate names
        '[[volumes]]\nname = "dup"\ntarget = "a"\n[[volumes]]\nname = "dup"\ntarget = "b"',
        # typo'd backup key — must not silently still back the volume up
        '[[volumes]]\nname = "x"\ntarget = "data"\n[volumes.backup]\ninclide = false',
    ],
)
def test_invalid_volumes_rejected(toml):
    with pytest.raises(Hop3TomlValidationError):
        validate_hop3_toml(tomllib.loads(toml))
