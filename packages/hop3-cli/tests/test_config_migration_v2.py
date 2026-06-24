# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Second migration: config.toml [contexts.*] -> token store (ADR 042 r2, F1).

The conftest points ``$HOP3_CONFIG_DIR`` at a per-test tmp dir; both config.toml
and the credential store live there, so the migration and the store agree.
"""

from __future__ import annotations

import pytest
import tomllib
from hop3_cli.core import credential_store as cs
from hop3_cli.core.config_migration_v2 import (
    BACKUP_SUFFIX,
    MigrationError,
    migrate_config_to_token_store,
)
from hop3_cli.core.paths import config_dir

# A typical post-stage-1 config.toml: [contexts.*] with url/token + api_* mirror.
_CFG = """
theme = "dark"

[cli]
current_context = "prod"

[contexts.prod]
url = "ssh://root@prod.example.com"
token = "eyJprod"
api_url = "ssh://root@prod.example.com"
api_token = "eyJprod"
protected = true

[contexts.dev]
url = "https://dev.example.com"
token = "eyJdev"
api_url = "https://dev.example.com"
api_token = "eyJdev"
"""


def _dir():
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write(text: str):
    d = _dir()
    (d / "config.toml").write_text(text)
    return d


def _config_text(d):
    return (d / "config.toml").read_text()


def test_drains_tokens_leaves_secret_free():
    d = _write(_CFG)
    notes = migrate_config_to_token_store(d)

    # Tokens drained to the store, canonical-keyed.
    assert cs.get_token("ssh://root@prod.example.com") == "eyJprod"
    assert cs.get_token("https://dev.example.com") == "eyJdev"

    cfg = tomllib.loads(_config_text(d))
    # Named contexts KEPT, but address-only (ADR 042 unified model) — so
    # `--context prod` still selects them. No token anywhere in the file.
    assert cfg["contexts"]["prod"] == {"server": "ssh://root@prod.example.com"}
    assert cfg["contexts"]["dev"] == {"server": "https://dev.example.com"}
    assert "current_context" not in cfg.get("cli", {})
    assert "eyJ" not in _config_text(d)  # no token anywhere in the file
    assert "protected" not in _config_text(d)  # r1 cruft dropped
    # Default *context* seeded from the old current-context name.
    assert cfg["cli"]["default_context"] == "prod"
    assert cfg["theme"] == "dark"  # unrelated prefs preserved
    assert notes


def test_https_token_preserved():
    # https can't SSH-re-auth, so its token MUST survive in the store.
    d = _write(_CFG)
    migrate_config_to_token_store(d)
    assert cs.get_token("https://dev.example.com") == "eyJdev"


def test_backup_holds_the_original():
    d = _write(_CFG)
    migrate_config_to_token_store(d)
    backup = d / ("config.toml" + BACKUP_SUFFIX)
    assert backup.exists()
    assert "eyJprod" in backup.read_text()  # original, tokens intact


def test_idempotent_exact_noop():
    d = _write(_CFG)
    migrate_config_to_token_store(d)
    after = _config_text(d)
    notes2 = migrate_config_to_token_store(d)
    assert notes2 == []
    assert _config_text(d) == after  # byte-identical: zero writes


def test_no_config_is_noop():
    assert migrate_config_to_token_store(_dir()) == []


def test_no_contexts_is_noop():
    d = _write('[cli]\ntheme = "dark"\n')
    assert migrate_config_to_token_store(d) == []


def test_malformed_aborts_unchanged():
    d = _write("not valid = = toml [[[")
    before = _config_text(d)
    with pytest.raises(MigrationError):
        migrate_config_to_token_store(d)
    assert _config_text(d) == before  # nothing changed
    assert cs.known_servers() == []  # store untouched
