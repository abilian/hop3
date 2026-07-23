# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for `hop3 app upgrade` / `hop3 app rollback` (M3.2).

These pin the TRANSACTION — snapshot, redeploy, auto-rollback on failure — with
do_deploy, BackupManager, and get_app stubbed, so the sequencing (not a real
build) is under test.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

import hop3.commands.app as app_module
from hop3.commands.app import AppRollbackCmd, AppUpgradeCmd


class _FakeManager:
    def __init__(self, backups=None, backup_app_name="myapp"):
        self.created = False
        self.restored = None
        self.restore_raises: Exception | None = None
        self.backup_app_name = backup_app_name  # who an explicit --to id belongs to
        self._backups = (
            backups if backups is not None else [SimpleNamespace(backup_id="B_LATEST")]
        )

    def create_backup(self, app, *, include_addons=True):
        self.created = True
        return "BK1", "/backups/BK1"

    def restore_backup(self, backup_id):
        if self.restore_raises:
            raise self.restore_raises
        self.restored = backup_id

    def list_backups(self, app_name, limit=20):
        return self._backups

    def get_backup_info(self, backup_id):
        return SimpleNamespace(app_name=self.backup_app_name, backup_id=backup_id)


@pytest.fixture
def env(monkeypatch):
    """Stub do_deploy / get_app / _backup_manager; hand back the recorders."""
    manager = _FakeManager()
    app = SimpleNamespace(name="myapp", last_deployed_at=datetime.now(UTC))
    session = SimpleNamespace(commit=lambda: None, rollback=lambda: None)
    monkeypatch.setattr(app_module, "get_app", lambda _s, _n: app)
    monkeypatch.setattr(app_module, "_backup_manager", lambda _s: manager)
    monkeypatch.setattr(app_module, "do_deploy", lambda _a, db_session=None: None)
    return SimpleNamespace(manager=manager, app=app, session=session, module=app_module)


def _types(items):
    return [it["t"] for it in items]


def _joined(items):
    return " ".join(str(it.get("text", "")) for it in items)


# ---- upgrade ----------------------------------------------------------------


def test_upgrade_success_takes_backup_and_deploys(env):
    result = AppUpgradeCmd(db_session=env.session).call("--app", "myapp")
    assert env.manager.created is True
    assert env.manager.restored is None  # no rollback on success
    assert "summary" in _types(result)
    assert "upgraded" in _joined(result)
    assert "BK1" in _joined(result)  # reports the pre-upgrade backup id


def test_upgrade_rolls_back_on_deploy_failure(env, monkeypatch):
    def boom(_app, db_session=None):
        msg = "healthcheck timeout"
        raise RuntimeError(msg)

    monkeypatch.setattr(env.module, "do_deploy", boom)

    with pytest.raises(ValueError, match="rolled back") as exc:
        AppUpgradeCmd(db_session=env.session).call("--app", "myapp")

    assert env.manager.restored == "BK1"  # restored the pre-upgrade snapshot
    assert "BK1" in str(exc.value)
    assert "healthcheck timeout" in str(exc.value)


def test_upgrade_reports_both_when_rollback_also_fails(env, monkeypatch):
    def boom(_app, db_session=None):
        msg = "healthcheck timeout"
        raise RuntimeError(msg)

    monkeypatch.setattr(env.module, "do_deploy", boom)
    env.manager.restore_raises = RuntimeError("restore broke")

    with pytest.raises(ValueError, match="ALSO FAILED") as exc:
        AppUpgradeCmd(db_session=env.session).call("--app", "myapp")
    msg = str(exc.value)
    assert "healthcheck timeout" in msg  # the upgrade error
    assert "restore broke" in msg  # the rollback error
    assert "hop3 backup restore" in msg  # a manual path — never a fake OK


def test_upgrade_refuses_never_deployed_app(env, monkeypatch):
    monkeypatch.setattr(
        env.module,
        "get_app",
        lambda _s, _n: SimpleNamespace(name="fresh", last_deployed_at=None),
    )
    with pytest.raises(ValueError, match="never been deployed"):
        AppUpgradeCmd(db_session=env.session).call("--app", "fresh")
    assert env.manager.created is False  # refused before taking a backup


def test_upgrade_requires_app_flag(env):
    with pytest.raises(ValueError, match="Usage"):
        AppUpgradeCmd(db_session=env.session).call()


# ---- rollback ---------------------------------------------------------------


def test_rollback_restores_the_most_recent_backup(env):
    result = AppRollbackCmd(db_session=env.session).call("--app", "myapp")
    assert env.manager.restored == "B_LATEST"
    assert "rolled back" in _joined(result)
    assert "summary" in _types(result)


def test_rollback_restores_an_explicit_backup(env):
    AppRollbackCmd(db_session=env.session).call("--app", "myapp", "--to", "20260101_x")
    assert env.manager.restored == "20260101_x"


def test_rollback_fails_loud_when_no_backup(env, monkeypatch):
    monkeypatch.setattr(
        env.module, "_backup_manager", lambda _s: _FakeManager(backups=[])
    )
    with pytest.raises(ValueError, match="No backup"):
        AppRollbackCmd(db_session=env.session).call("--app", "myapp")


def test_rollback_refuses_a_backup_from_another_app(env, monkeypatch):
    # An explicit --to id belonging to a different app must be refused, not
    # silently restored — restore_backup targets the backup's OWN app, so this
    # would stop+overwrite that other app while reporting myapp was rolled back.
    monkeypatch.setattr(
        env.module, "_backup_manager", lambda _s: _FakeManager(backup_app_name="other")
    )
    with pytest.raises(ValueError, match="belongs to app 'other'"):
        AppRollbackCmd(db_session=env.session).call("--app", "myapp", "--to", "foreign")


def test_rollback_requires_app_flag(env):
    with pytest.raises(ValueError, match="Usage"):
        AppRollbackCmd(db_session=env.session).call()


def test_rollback_is_destructive():
    # Overwrites live data -> the CLI must add a confirmation gate.
    assert AppRollbackCmd.destructive is True
