# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Stage 3: every target is a named context, and one key says which is current.

`[cli].default_server` was an *unnamed* default target that `get_api_url`
consults below every context, so an operator with any context at all had it
silently ignored — while `hop3 login` reported success writing it. And "which
context is current" had two keys read by two functions that disagreed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import tomllib
from hop3_cli.core.config_migration_v2 import MigrationError
from hop3_cli.core.config_migration_v3 import BACKUP_SUFFIX, migrate_to_named_targets

if TYPE_CHECKING:
    from pathlib import Path


def migrate(tmp_path: Path, toml_text: str) -> tuple[list[str], dict]:
    (tmp_path / "config.toml").write_text(toml_text)
    notes = migrate_to_named_targets(tmp_path)
    with (tmp_path / "config.toml").open("rb") as f:
        return notes, tomllib.load(f)


class TestUnnamedDefaultServer:
    def test_becomes_the_default_context(self, tmp_path):
        notes, cfg = migrate(tmp_path, '[cli]\ndefault_server = "ssh://root@a.com"\n')
        assert cfg["contexts"]["default"]["server"] == "ssh://root@a.com"
        assert cfg["cli"]["default_context"] == "default"
        assert "default_server" not in cfg["cli"]
        assert "ssh://root@a.com" in notes[0]

    def test_reuses_a_context_that_already_names_it(self, tmp_path):
        notes, cfg = migrate(
            tmp_path,
            '[cli]\ndefault_server = "ssh://root@a.com"\n'
            '[contexts.prod]\nserver = "ssh://root@a.com"\n',
        )
        assert "default" not in cfg["contexts"], "no duplicate for one address"
        assert cfg["cli"]["default_context"] == "prod"
        assert "prod" in notes[0]

    def test_dropped_when_a_context_already_outranks_it(self, tmp_path):
        """It was unreachable: every context resolves above `default_server`."""
        notes, cfg = migrate(
            tmp_path,
            '[cli]\ndefault_server = "ssh://root@dead.com"\ndefault_context = "prod"\n'
            '[contexts.default]\nserver = "ssh://root@b.com"\n'
            '[contexts.prod]\nserver = "ssh://root@p.com"\n',
        )
        assert cfg["cli"]["default_context"] == "prod"
        assert "default_server" not in cfg["cli"]
        assert cfg["contexts"]["default"]["server"] == "ssh://root@b.com"
        assert "unreachable" in notes[0]

    def test_ambiguous_config_aborts_and_changes_nothing(self, tmp_path):
        """`default` names another server and nothing is current: unresolvable."""
        text = (
            '[cli]\ndefault_server = "ssh://root@a.com"\n'
            '[contexts.default]\nserver = "ssh://root@b.com"\n'
        )
        (tmp_path / "config.toml").write_text(text)
        with pytest.raises(MigrationError) as excinfo:
            migrate_to_named_targets(tmp_path)
        assert "ambiguous" in str(excinfo.value)
        assert (tmp_path / "config.toml").read_text() == text, "nothing changed"


class TestCurrentContextPointer:
    def test_adopted_when_it_names_a_real_context(self, tmp_path):
        notes, cfg = migrate(
            tmp_path,
            '[cli]\ncurrent_context = "prod"\n[contexts.prod]\nserver = "s"\n',
        )
        assert cfg["cli"]["default_context"] == "prod"
        assert "current_context" not in cfg["cli"]
        assert "prod" in notes[0]

    def test_a_top_level_pointer_is_read_too(self, tmp_path):
        _, cfg = migrate(
            tmp_path, 'current_context = "prod"\n[contexts.prod]\nserver = "s"\n'
        )
        assert cfg["cli"]["default_context"] == "prod"
        assert "current_context" not in cfg

    def test_dangling_pointer_is_dropped_and_reported(self, tmp_path):
        """Stage 2 skips a config with no [contexts]; the pointer stayed behind."""
        notes, cfg = migrate(tmp_path, '[cli]\ncurrent_context = "gone"\n')
        assert cfg == {}
        assert notes
        assert "no context has that name" in notes[0]

    def test_never_overrides_a_live_default_context(self, tmp_path):
        notes, cfg = migrate(
            tmp_path,
            '[cli]\ncurrent_context = "prod"\ndefault_context = "dev"\n'
            '[contexts.prod]\nserver = "p"\n[contexts.dev]\nserver = "d"\n',
        )
        assert cfg["cli"]["default_context"] == "dev"
        assert notes
        assert "already in effect" in notes[0]


class TestContract:
    def test_no_op_on_an_already_migrated_config(self, tmp_path):
        text = '[cli]\ndefault_context = "default"\n[contexts.default]\nserver = "s"\n'
        notes, _ = migrate(tmp_path, text)
        assert notes == []
        assert not (tmp_path / ("config.toml" + BACKUP_SUFFIX)).exists(), (
            "a no-op writes nothing at all"
        )

    def test_no_op_without_a_config_file(self, tmp_path):
        assert migrate_to_named_targets(tmp_path) == []

    def test_backs_up_before_writing(self, tmp_path):
        text = '[cli]\ndefault_server = "ssh://root@a.com"\n'
        migrate(tmp_path, text)
        assert (tmp_path / ("config.toml" + BACKUP_SUFFIX)).read_text() == text

    def test_malformed_toml_aborts_and_changes_nothing(self, tmp_path):
        (tmp_path / "config.toml").write_text("this is [not toml")
        with pytest.raises(MigrationError):
            migrate_to_named_targets(tmp_path)
        assert (tmp_path / "config.toml").read_text() == "this is [not toml"

    def test_is_idempotent(self, tmp_path):
        migrate(tmp_path, '[cli]\ndefault_server = "ssh://root@a.com"\n')
        notes = migrate_to_named_targets(tmp_path)
        assert notes == []

    def test_unrelated_settings_survive(self, tmp_path):
        _, cfg = migrate(
            tmp_path,
            'verify_ssl = "false"\n[cli]\ndefault_server = "s"\nverbosity = 2\n',
        )
        assert cfg["verify_ssl"] == "false"
        assert cfg["cli"]["verbosity"] == 2
