# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Tests for the new 4-command `hop3 system` surface.

The pre-0.5 commands ``check`` / ``uptime`` / ``ps`` were removed and
``check`` was renamed to ``status``. Tests focus on:

- Rendering correctness (icon-from-severity, summary-from-counts).
- Mode flags: default, ``--quiet``, ``--json``.
- Regressions for the two bugs the redesign fixed:
    - icon mismatched the underlying state
    - "All checks passed" printed despite warnings
"""

from __future__ import annotations

import json

import pytest

from hop3.commands import system as sysmod
from hop3.commands.system import (
    _SEVERITY_ICON,
    CheckItem,
    CheckSection,
    InfoCmd,
    StatusCmd,
    _worst,
)
from hop3.core.protocols import HealthCheckResult

IDENTITY = {
    "hostname": "test-host",
    "ip": "10.0.0.1",
    "version": "0.5.0.dev3",
    "uptime": "1d 2h",
}


# ---------------------------------------------------------------------------
# HealthCheckResult.derived_severity
# ---------------------------------------------------------------------------


def test_derived_severity_defaults_from_passed():
    assert (
        HealthCheckResult(name="X", passed=True, message="m").derived_severity == "ok"
    )
    assert (
        HealthCheckResult(name="X", passed=False, message="m").derived_severity
        == "fail"
    )


def test_derived_severity_honours_explicit_value():
    # Regression: an unreachable optional service should render ⚠, not ✓ or ✗.
    r = HealthCheckResult(name="X", passed=False, severity="warn", message="m")
    assert r.derived_severity == "warn"


# ---------------------------------------------------------------------------
# _worst
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("severities", "expected"),
    [
        ([], "ok"),
        (["ok"], "ok"),
        (["ok", "warn"], "warn"),
        (["warn", "ok"], "warn"),
        (["ok", "warn", "fail"], "fail"),
        (["fail", "ok"], "fail"),
    ],
)
def test_worst(severities, expected):
    assert _worst(severities) == expected


# ---------------------------------------------------------------------------
# StatusCmd rendering
# ---------------------------------------------------------------------------


def _all_ok_sections():
    return [
        CheckSection(
            "Services",
            [
                CheckItem("Nginx", "ok", "running"),
                CheckItem("hop3-server", "ok", "running"),
            ],
        ),
        CheckSection(
            "Filesystem",
            [CheckItem("HOP3_ROOT", "ok", "writable")],
        ),
    ]


def _mixed_sections():
    return [
        CheckSection(
            "Services",
            [CheckItem("Nginx", "ok", "running")],
        ),
        CheckSection(
            "Backing services",
            [
                CheckItem("PostgreSQL", "ok", "ok"),
                CheckItem("Redis", "warn", "unreachable"),
            ],
        ),
        CheckSection(
            "Disk",
            [CheckItem("Disk usage", "fail", "92%")],
        ),
    ]


def test_render_rich_includes_identity_line():
    cmd = StatusCmd()
    result = cmd._render_rich(IDENTITY, _all_ok_sections(), "ok")
    blob = result[0]["text"]
    assert "test-host" in blob
    assert "10.0.0.1" in blob
    assert "v0.5.0.dev3" in blob
    assert "1d 2h" in blob


def test_render_rich_uses_no_hardcoded_dividers():
    """Regression: the old impl baked '=' and '-' lines into the output."""
    cmd = StatusCmd()
    result = cmd._render_rich(IDENTITY, _all_ok_sections(), "ok")
    blob = result[0]["text"]
    assert "===" not in blob
    assert "---" not in blob


def test_render_rich_icon_matches_severity():
    """Regression: the old impl showed ✓ on items it had marked failed."""
    cmd = StatusCmd()
    result = cmd._render_rich(IDENTITY, _mixed_sections(), "fail")
    blob = result[0]["text"]
    # Redis is warn → must show ⚠ (not ✓)
    assert "Redis" in blob
    redis_line = next(line for line in blob.splitlines() if "Redis" in line)
    assert _SEVERITY_ICON["warn"] in redis_line
    assert _SEVERITY_ICON["ok"] not in redis_line
    # Disk is fail → must show ✗
    disk_line = next(line for line in blob.splitlines() if "Disk usage" in line)
    assert _SEVERITY_ICON["fail"] in disk_line


def test_render_rich_summary_counts_warnings_and_failures():
    """Regression: the old impl printed '✓ All checks passed' despite warnings."""
    cmd = StatusCmd()
    result = cmd._render_rich(IDENTITY, _mixed_sections(), "fail")
    # The summary is appended as the last response item.
    summary = result[-1]
    assert summary["t"] == "error"  # overall == fail → error item
    assert "1 failure" in summary["text"]
    assert "1 warning" in summary["text"]
    assert "All OK" not in summary["text"]


def test_render_rich_all_ok_says_so():
    cmd = StatusCmd()
    result = cmd._render_rich(IDENTITY, _all_ok_sections(), "ok")
    summary = result[-1]
    assert summary["t"] == "success"
    assert "all OK" in summary["text"]


def test_render_rich_warn_only_uses_warning_item():
    cmd = StatusCmd()
    sections = [CheckSection("S", [CheckItem("X", "warn", "soft")])]
    result = cmd._render_rich(IDENTITY, sections, "warn")
    assert result[-1]["t"] == "warning"
    assert "1 warning" in result[-1]["text"]


# ---------------------------------------------------------------------------
# Mode flags
# ---------------------------------------------------------------------------


def test_quiet_ok_returns_single_success_item():
    cmd = StatusCmd()
    out = cmd._render_quiet("ok", _all_ok_sections())
    assert out["t"] == "success"
    assert out["text"] == "OK"


def test_quiet_warn_returns_warning_with_detail():
    cmd = StatusCmd()
    out = cmd._render_quiet("warn", _mixed_sections())
    # warn doesn't trigger fail → still warning, not error
    # but our _mixed_sections has a fail; quiet should pick from passed overall arg
    sections = [
        CheckSection("S", [CheckItem("Redis", "warn", "unreachable")]),
    ]
    out = cmd._render_quiet("warn", sections)
    assert out["t"] == "warning"
    assert "DEGRADED" in out["text"]
    assert "redis" in out["text"].lower()


def test_quiet_fail_returns_error():
    cmd = StatusCmd()
    out = cmd._render_quiet("fail", _mixed_sections())
    assert out["t"] == "error"
    assert "FAILED" in out["text"]


def test_to_json_is_round_trippable():
    cmd = StatusCmd()
    payload = cmd._to_json(IDENTITY, _mixed_sections(), "fail")
    # Must be JSON-serializable
    serialized = json.dumps(payload)
    parsed = json.loads(serialized)
    assert parsed["overall"] == "fail"
    assert parsed["identity"]["hostname"] == "test-host"
    titles = [s["title"] for s in parsed["sections"]]
    assert "Services" in titles
    assert "Backing services" in titles
    redis = next(
        item
        for s in parsed["sections"]
        for item in s["items"]
        if item["name"] == "Redis"
    )
    assert redis["severity"] == "warn"


# ---------------------------------------------------------------------------
# InfoCmd
# ---------------------------------------------------------------------------


def test_info_returns_facts_only():
    """No liveness probes — facts only."""
    cmd = InfoCmd()
    result = cmd.call()
    # Response is a single text item.
    assert len(result) == 1
    blob = result[0]["text"]
    assert "Version:" in blob
    assert "Python:" in blob
    assert "Platform:" in blob
    assert "Hostname:" in blob


def test_info_reports_server_uptime_db_and_tls_engine():
    """Audit facts beyond the host: server-process uptime, DB backend, TLS engine."""
    blob = InfoCmd().call()[0]["text"]
    # Host vs server uptime are distinct lines (server resets on restart).
    assert "Host uptime:" in blob
    assert "Server uptime:" in blob
    # Control-plane backend and the TLS engine actually in effect.
    assert "Database:" in blob
    assert "TLS engine:" in blob
    assert "Features:" in blob


def test_info_features_lists_installed_addons(tmp_path, monkeypatch):
    """
    `Features` is derived from the installer footprint: addon creds in
    hop3-server.toml mark postgres/mysql as installed.
    """
    (tmp_path / "hop3-server.toml").write_text(
        'POSTGRES_SUPERUSER_PASSWORD = "x"\nMYSQL_SUPERUSER_PASSWORD = "y"\n'
    )
    monkeypatch.setattr(sysmod, "HOP3_ROOT", tmp_path)

    features = sysmod._installed_features()
    assert "postgres" in features
    assert "mysql" in features


def test_info_features_none_without_addons(tmp_path, monkeypatch):
    (tmp_path / "hop3-server.toml").write_text('HOP3_SECRET_KEY = "x"\n')
    monkeypatch.setattr(sysmod, "HOP3_ROOT", tmp_path)
    # No postgres/mysql creds → neither reported (redis/s3/nix depend on the host).
    features = sysmod._installed_features()
    assert "postgres" not in features
    assert "mysql" not in features


def test_database_backend_reports_scheme_not_credentials(monkeypatch):
    # Never leak a Postgres password into `system info` — scheme only.
    monkeypatch.setenv("HOP3_DATABASE_URI", "postgresql://u:secret@host/db")
    assert sysmod._database_backend() == "postgresql"
    monkeypatch.delenv("HOP3_DATABASE_URI", raising=False)
    assert sysmod._database_backend() == "sqlite"


def test_info_verbose_lists_plugins():
    cmd = InfoCmd()
    result = cmd.call("-v")
    blob = result[0]["text"]
    assert "Loaded plugins" in blob
    # Header sections inside verbose output.
    assert "Builders" in blob
    assert "Deployers" in blob
    assert "Toolchains" in blob


def test_info_shows_provenance_from_manifest(tmp_path, monkeypatch):
    """`system info` surfaces the deploy manifest's commit/branch/method."""
    (tmp_path / "build-info.json").write_text(
        json.dumps({
            "version": "0.5.0",
            "deploy_method": "local",
            "git_commit": "abc123def4567890",
            "git_branch": "feat/cli-help-full",
            "git_dirty": True,
            "deployed_by": "hop3-deploy",
            "deployed_at": "2026-06-12T10:30:00+00:00",
        })
    )
    monkeypatch.setattr(sysmod, "HOP3_ROOT", tmp_path)

    blob = InfoCmd().call()[0]["text"]
    assert "Commit:         abc123def4567890 (dirty)" in blob
    assert "Branch:         feat/cli-help-full" in blob
    assert "Deploy method:  local" in blob
    assert "Deployed:       2026-06-12T10:30:00+00:00" in blob


def test_info_provenance_unknown_without_manifest(tmp_path, monkeypatch):
    """With no manifest (and no VCS install), Commit reads 'unknown'."""
    monkeypatch.setattr(sysmod, "HOP3_ROOT", tmp_path)
    monkeypatch.setattr(sysmod, "_commit_from_direct_url", lambda: (None, None))

    blob = InfoCmd().call()[0]["text"]
    assert "Commit:         unknown" in blob
    # Absent optional fields are simply not shown.
    assert "Branch:" not in blob
    assert "Deployed:" not in blob


def test_provenance_falls_back_to_direct_url(tmp_path, monkeypatch):
    """No manifest but a git (PEP 610) install → commit from direct_url.json."""
    monkeypatch.setattr(sysmod, "HOP3_ROOT", tmp_path)
    monkeypatch.setattr(
        sysmod, "_commit_from_direct_url", lambda: ("deadbeefcafe", "devel")
    )

    lines = sysmod._provenance_lines()
    assert "Commit:         deadbeefcafe" in lines
    assert "Branch:         devel" in lines


# ---------------------------------------------------------------------------
# Removed commands — ensure they don't load at import time
# ---------------------------------------------------------------------------


def test_removed_commands_are_gone():
    assert not hasattr(sysmod, "UptimeCmd")
    assert not hasattr(sysmod, "PSCmd")
    assert not hasattr(sysmod, "CheckCmd")
