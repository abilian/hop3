# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the audit log writer."""

from __future__ import annotations

import json

from hop3_rootd.audit import (
    AuditEntry,
    AuditLog,
    sanitise_args,
)

# --- sanitise_args --------------------------------------------------------


def test_sanitise_keeps_normal_fields():
    assert sanitise_args({"port": 8448, "protocol": "tcp"}) == {
        "port": 8448,
        "protocol": "tcp",
    }


def test_sanitise_redacts_password_field():
    out = sanitise_args({"port": 80, "password": "hunter2"})
    assert out["port"] == 80
    assert out["password"] == "<redacted>"


def test_sanitise_redacts_token_field():
    out = sanitise_args({"api_token": "abc123"})
    assert out["api_token"] == "<redacted>"


def test_sanitise_redacts_secret_field():
    out = sanitise_args({"client_secret": "shh"})
    assert out["client_secret"] == "<redacted>"


def test_sanitise_redacts_key_field():
    """'key' itself, plus 'api_key', 'api-key', 'apikey'."""
    assert sanitise_args({"key": "k"})["key"] == "<redacted>"
    assert sanitise_args({"api_key": "k"})["api_key"] == "<redacted>"
    assert sanitise_args({"api-key": "k"})["api-key"] == "<redacted>"
    assert sanitise_args({"apikey": "k"})["apikey"] == "<redacted>"


def test_sanitise_redacts_credential_field():
    assert sanitise_args({"db_credential": "v"})["db_credential"] == "<redacted>"


def test_sanitise_case_insensitive():
    """Field-name match is case-insensitive."""
    assert sanitise_args({"PASSWORD": "v"})["PASSWORD"] == "<redacted>"
    assert sanitise_args({"Token": "v"})["Token"] == "<redacted>"


def test_sanitise_recurses_into_dicts():
    out = sanitise_args({
        "outer": {"password": "hunter2", "port": 80},
        "port": 5432,
    })
    assert out["outer"]["password"] == "<redacted>"
    assert out["outer"]["port"] == 80
    assert out["port"] == 5432


def test_sanitise_does_not_mutate_input():
    inp = {"password": "hunter2", "port": 80}
    sanitise_args(inp)
    assert inp["password"] == "hunter2"


def test_sanitise_redacts_inside_lists_of_dicts():
    """
    A list of dicts containing secret keys must redact each member.

    Today's rootd ops are flat dicts, but the sanitiser is the safety
    net for future ops — a list of credential records must redact the
    same way a single dict does.
    """
    out = sanitise_args({
        "configs": [
            {"name": "a", "password": "p1"},
            {"name": "b", "api_token": "t1"},
        ],
    })
    assert out["configs"][0] == {"name": "a", "password": "<redacted>"}
    assert out["configs"][1] == {"name": "b", "api_token": "<redacted>"}


def test_sanitise_redacts_inside_nested_tuples():
    """Tuples nest the same way as lists."""
    out = sanitise_args({"creds": ({"password": "p1"}, {"password": "p2"})})
    assert out["creds"] == ({"password": "<redacted>"}, {"password": "<redacted>"})


def test_sanitise_top_level_list():
    """Calling with a top-level list returns a list (not coerced to dict)."""
    out = sanitise_args([{"password": "p1"}, {"name": "x"}])
    assert out == [{"password": "<redacted>"}, {"name": "x"}]


def test_sanitise_passes_scalars_through():
    """Non-container values round-trip unchanged."""
    assert sanitise_args(42) == 42
    assert sanitise_args("abc") == "abc"
    assert sanitise_args(None) is None


def test_sanitise_redacts_secret_substrings_anywhere():
    """
    The pattern matches secret words anywhere in the field name.

    Previously the regex used a ``$`` end-anchor and missed
    ``aws_access_key_id`` and similar (where the secret-marker word is
    not the trailing component). Per the security-review policy
    "false-positives are fine, false-negatives leak", we widened the
    pattern. Side effect: an innocent field whose name happens to
    contain ``key``/``token``/etc. (e.g. ``portkey_admin``) also gets
    redacted. That is the cost of safety-first coverage and is not a
    correctness issue — the audit log still records the operation,
    just with the suspect field censored.
    """
    out = sanitise_args({
        "aws_access_key_id": "AKIA...",
        "aws_secret_access_key": "sek",
        "private_key": "-----BEGIN...-----",
        "passphrase": "open sesame",
        "portkey_admin": "innocent-but-redacted",
    })
    assert out["aws_access_key_id"] == "<redacted>"
    assert out["aws_secret_access_key"] == "<redacted>"
    assert out["private_key"] == "<redacted>"
    assert out["passphrase"] == "<redacted>"
    # Conservative widening: an innocent field containing "key" is also
    # redacted. We accept this in exchange for catching the AWS-style names.
    assert out["portkey_admin"] == "<redacted>"


# --- AuditEntry.to_json_line ---------------------------------------------


def test_entry_serialises_to_one_line():
    entry = AuditEntry(
        ts="2026-04-24T15:30:00Z",
        request_id="r1",
        caller_uid=1000,
        op="firewall.add_rule",
        args={"port": 8448, "protocol": "tcp"},
        outcome="applied",
        duration_ms=12,
        result={"rule_id": "rule-7f3a"},
    )
    line = entry.to_json_line()
    assert "\n" not in line
    parsed = json.loads(line)
    assert parsed["op"] == "firewall.add_rule"
    assert parsed["result"] == {"rule_id": "rule-7f3a"}
    assert "error" not in parsed


def test_entry_serialises_error():
    entry = AuditEntry(
        ts="2026-04-24T15:30:00Z",
        request_id="r1",
        caller_uid=1000,
        op="firewall.add_rule",
        args={"port": 99999},
        outcome="error",
        duration_ms=3,
        error={"code": "validation_failed", "message": "out of range"},
    )
    parsed = json.loads(entry.to_json_line())
    assert parsed["outcome"] == "error"
    assert parsed["error"]["code"] == "validation_failed"
    assert "result" not in parsed


def test_entry_omits_unset_result_and_error():
    entry = AuditEntry(
        ts="2026-04-24T15:30:00Z",
        request_id="r1",
        caller_uid=1000,
        op="daemon.health",
        args={},
        outcome="applied",
        duration_ms=1,
    )
    parsed = json.loads(entry.to_json_line())
    assert "result" not in parsed
    assert "error" not in parsed


# --- AuditLog file writes ------------------------------------------------


def test_audit_log_appends_lines(tmp_path):
    path = tmp_path / "audit.log"
    log = AuditLog(path)

    log.write(
        AuditEntry(
            ts="2026-04-24T15:30:00Z",
            request_id="r1",
            caller_uid=1000,
            op="daemon.health",
            args={},
            outcome="applied",
            duration_ms=1,
        )
    )
    log.write(
        AuditEntry(
            ts="2026-04-24T15:30:01Z",
            request_id="r2",
            caller_uid=1000,
            op="firewall.list_rules",
            args={},
            outcome="applied",
            duration_ms=2,
        )
    )
    log.close()

    content = path.read_text()
    lines = content.strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["request_id"] == "r1"
    assert json.loads(lines[1])["request_id"] == "r2"


def test_audit_log_creates_parent_dir(tmp_path):
    path = tmp_path / "subdir" / "audit.log"
    log = AuditLog(path)
    log.write(
        AuditEntry(
            ts="2026-04-24T15:30:00Z",
            request_id="r1",
            caller_uid=1000,
            op="daemon.health",
            args={},
            outcome="applied",
            duration_ms=1,
        )
    )
    log.close()
    assert path.exists()


def test_audit_log_reopen_continues_appending(tmp_path):
    """SIGUSR1 → reopen() must not lose subsequent writes."""
    path = tmp_path / "audit.log"
    log = AuditLog(path)
    log.write(_entry("r1"))
    log.reopen()
    log.write(_entry("r2"))
    log.close()
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 2


def test_audit_log_context_manager(tmp_path):
    path = tmp_path / "audit.log"
    with AuditLog(path) as log:
        log.write(_entry("r1"))
    # After context exit, file is closed but contents preserved.
    assert path.read_text().strip()


def test_audit_log_file_mode(tmp_path):
    """New audit log gets mode 0640 (group hop3 readable)."""
    path = tmp_path / "audit.log"
    log = AuditLog(path)
    log.write(_entry("r1"))
    log.close()
    mode = path.stat().st_mode & 0o777
    assert mode == 0o640


def test_audit_log_counts_fsync_failures(tmp_path, monkeypatch):
    """
    An fsync that fails (exotic FS) is counted and warned, not swallowed.

    The audit record itself still lands — flush() got it to the kernel buffer
    before fsync ran — so only durability-of-the-last-record is at risk, and
    that risk is now observable via ``fsync_failures`` instead of log noise.
    """
    path = tmp_path / "audit.log"
    log = AuditLog(path)

    def boom(_fd: int) -> None:
        raise OSError  # message is irrelevant; the test checks the counter

    monkeypatch.setattr("hop3_rootd.audit.os.fsync", boom)
    log.write(_entry("r1"))  # must not raise
    log.close()

    assert log.fsync_failures == 1
    # The entry was still written.
    assert path.read_text().strip()


# --- Helpers --------------------------------------------------------------


def _entry(request_id: str) -> AuditEntry:
    return AuditEntry(
        ts="2026-04-24T15:30:00Z",
        request_id=request_id,
        caller_uid=1000,
        op="daemon.health",
        args={},
        outcome="applied",
        duration_ms=1,
    )
