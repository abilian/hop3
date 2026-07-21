# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the vendored-dependency hash helper."""

from __future__ import annotations

import pytest
from hop3_tooling.nix_hash import (
    PLACEHOLDER_HASH,
    hash_key_for,
    parse_nix_hash_mismatch,
    set_nix_hash,
)

REAL = "sha256-XmpLKqW1uYs3vT0pQ9rB4cD5eF6gH7iJ8kL9mN0oP1Q="

NIX_ERROR = f"""\
error: hash mismatch in fixed-output derivation '/nix/store/abc-isso-python-deps.drv':
         specified: {PLACEHOLDER_HASH}
            got:    {REAL}
"""


def test_reads_the_reported_hash():
    assert parse_nix_hash_mismatch(NIX_ERROR) == REAL


def test_does_not_return_the_placeholder_we_sent_in():
    """`specified:` is our placeholder; only `got:` is the answer."""
    assert parse_nix_hash_mismatch(NIX_ERROR) != PLACEHOLDER_HASH


def test_absent_mismatch_returns_none():
    assert parse_nix_hash_mismatch("error: build failed, disk full") is None


def test_sets_an_existing_key_in_place():
    toml = '[nix]\ntemplate = "python-venv"\npip-deps-hash = "sha256-old="\n'
    out = set_nix_hash(toml, "pip-deps-hash", REAL)
    assert f'pip-deps-hash = "{REAL}"' in out
    assert "sha256-old=" not in out


def test_inserts_a_missing_key_under_the_nix_table():
    toml = '[metadata]\nid = "isso"\n\n[nix]\ntemplate = "python-venv"\n'
    out = set_nix_hash(toml, "pip-deps-hash", REAL)
    assert f'[nix]\npip-deps-hash = "{REAL}"' in out


def test_comments_survive_the_rewrite():
    """These recipes carry explanatory comments a TOML round-trip would drop."""
    toml = '[nix]\n# why this template\ntemplate = "php-app"\n'
    out = set_nix_hash(toml, "composer-deps-hash", REAL)
    assert "# why this template" in out


def test_only_touches_the_nix_table():
    """A same-named key in another table must not be rewritten."""
    toml = '[other]\npip-deps-hash = "keep-me"\n\n[nix]\ntemplate = "python-venv"\n'
    out = set_nix_hash(toml, "pip-deps-hash", REAL)
    assert 'pip-deps-hash = "keep-me"' in out
    assert out.count(REAL) == 1


def test_rejects_a_recipe_with_no_nix_table():
    with pytest.raises(ValueError, match=r"no \[nix\] section"):
        set_nix_hash('[metadata]\nid = "x"\n', "pip-deps-hash", REAL)


@pytest.mark.parametrize(
    ("template", "key"),
    [
        ("python-venv", "pip-deps-hash"),
        ("php-app", "composer-deps-hash"),
        ("node-pnpm-install", "node-deps-hash"),
        ("go-source", "go-vendor-hash"),
    ],
)
def test_hash_key_per_template(template, key):
    assert hash_key_for(template) == key


def test_template_that_vendors_nothing_is_rejected():
    with pytest.raises(ValueError, match="vendors no dependencies"):
        hash_key_for("nixpkgs-wrapper")
