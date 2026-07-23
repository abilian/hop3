# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for state.json read/write."""

from __future__ import annotations

import json
import os

import pytest
from hop3_rootd.state import (
    STATE_VERSION,
    State,
    StateCorruptError,
    StateMissingError,
    StateVersionError,
    StoredRule,
    init_empty,
    load,
    save,
)

# --- Round-trip ---------------------------------------------------------


def test_save_then_load_empty(tmp_path):
    path = tmp_path / "state.json"
    save(State(version=STATE_VERSION, rules=[]), path)
    loaded = load(path)
    assert loaded.version == STATE_VERSION
    assert loaded.rules == []


def test_save_then_load_with_rules(tmp_path):
    path = tmp_path / "state.json"
    rule = StoredRule(
        rule_id="rule-7f3a",
        spec={"port": 8448, "protocol": "tcp", "source": "any", "app_name": "matrix"},
        applied_at="2026-04-24T15:30:00Z",
        status="applied",
    )
    save(State(version=STATE_VERSION, rules=[rule]), path)
    loaded = load(path)
    assert len(loaded.rules) == 1
    r = loaded.rules[0]
    assert r.rule_id == "rule-7f3a"
    assert r.spec["port"] == 8448
    assert r.applied_at == "2026-04-24T15:30:00Z"
    assert r.status == "applied"


def test_save_writes_atomic(tmp_path):
    """save() must use a tmp file then rename — no .tmp left after success."""
    path = tmp_path / "state.json"
    save(State(version=STATE_VERSION, rules=[]), path)
    # No leftover .tmp file
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == []


def test_save_creates_parent_dir(tmp_path):
    path = tmp_path / "subdir" / "state.json"
    save(State(version=STATE_VERSION, rules=[]), path)
    assert path.exists()


def test_save_pretty_prints(tmp_path):
    """Saved JSON is indented for human readability."""
    path = tmp_path / "state.json"
    save(State(version=STATE_VERSION, rules=[]), path)
    content = path.read_text()
    assert "\n" in content  # indented
    assert "  " in content  # 2-space indent


def test_save_sets_perms_0600(tmp_path):
    """
    The persisted state file is always mode 0o600 regardless of umask.

    The systemd StateDirectory= already restricts access at the dir
    level, but the file's own perms must be pinned in case the daemon
    is ever run outside systemd (tests, standalone) where the parent
    dir is wider.
    """
    path = tmp_path / "state.json"
    # Force a permissive umask to expose any reliance on the default.
    old_umask = os.umask(0o022)
    try:
        save(State(version=STATE_VERSION, rules=[]), path)
    finally:
        os.umask(old_umask)
    mode = path.stat().st_mode & 0o777
    assert mode == 0o600, f"expected 0o600, got 0o{mode:o}"


# --- Load errors --------------------------------------------------------


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(StateMissingError):
        load(tmp_path / "no-such-file.json")


def test_load_invalid_json_raises_corrupt(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not valid json")
    with pytest.raises(StateCorruptError):
        load(path)


def test_load_non_object_raises_corrupt(tmp_path):
    path = tmp_path / "state.json"
    path.write_text('["array", "not", "object"]')
    with pytest.raises(StateCorruptError, match="object"):
        load(path)


def test_load_missing_version_raises(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"rules": []}))
    with pytest.raises(StateVersionError, match="missing 'version'"):
        load(path)


def test_load_non_int_version_raises(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"version": "1", "rules": []}))
    with pytest.raises(StateVersionError, match="must be int"):
        load(path)


def test_load_unknown_version_raises(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"version": 999, "rules": []}))
    with pytest.raises(StateVersionError, match="unknown state version"):
        load(path)


def test_load_non_list_rules_raises(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"version": STATE_VERSION, "rules": "oops"}))
    with pytest.raises(StateCorruptError, match="'rules' must be a list"):
        load(path)


def test_load_malformed_rule_raises(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps({"version": STATE_VERSION, "rules": [{"missing": "fields"}]})
    )
    with pytest.raises(StateCorruptError, match="rules\\[0\\] is malformed"):
        load(path)


def test_load_non_object_rule_raises(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"version": STATE_VERSION, "rules": ["string"]}))
    with pytest.raises(StateCorruptError, match="rules\\[0\\] must be an object"):
        load(path)


def test_load_rules_default_status_is_applied(tmp_path):
    """status defaults to 'applied' if missing in the JSON."""
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps({
            "version": STATE_VERSION,
            "rules": [
                {
                    "rule_id": "r1",
                    "spec": {"port": 80},
                    "applied_at": "2026-04-24T00:00:00Z",
                }
            ],
        })
    )
    state = load(path)
    assert state.rules[0].status == "applied"


# --- State helpers ------------------------------------------------------


def test_find_rule():
    state = State(
        version=STATE_VERSION,
        rules=[
            StoredRule("r1", {"app_name": "a"}, "2026-04-24T00:00:00Z"),
            StoredRule("r2", {"app_name": "b"}, "2026-04-24T00:00:00Z"),
        ],
    )
    rule = state.find_rule("r1")
    assert rule is not None
    assert rule.spec["app_name"] == "a"
    assert state.find_rule("nonexistent") is None


def test_rules_for_app():
    state = State(
        version=STATE_VERSION,
        rules=[
            StoredRule(
                "r1", {"app_name": "matrix", "port": 8448}, "2026-04-24T00:00:00Z"
            ),
            StoredRule("r2", {"app_name": "other"}, "2026-04-24T00:00:00Z"),
            StoredRule(
                "r3", {"app_name": "matrix", "port": 3478}, "2026-04-24T00:00:00Z"
            ),
        ],
    )
    matrix_rules = state.rules_for_app("matrix")
    assert len(matrix_rules) == 2
    assert {r.rule_id for r in matrix_rules} == {"r1", "r3"}


# --- init_empty ---------------------------------------------------------


def test_init_empty_creates_file(tmp_path):
    path = tmp_path / "state.json"
    state = init_empty(path)
    assert path.exists()
    assert state.version == STATE_VERSION
    assert state.rules == []
    # And it's loadable.
    loaded = load(path)
    assert loaded.version == STATE_VERSION
