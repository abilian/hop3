# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for BackupManager DI integration."""

from __future__ import annotations

from hop3.core.backup import BackupManager


def test_backup_manager_from_container(di_container):
    """Test that BackupManager can be retrieved from DI container."""
    with di_container() as request_container:
        manager = request_container.get(BackupManager)

        assert isinstance(manager, BackupManager)
        assert manager.db_session is not None


def test_backup_manager_has_real_session(di_container):
    """Test that BackupManager gets a real SQLAlchemy session."""
    with di_container() as request_container:
        manager = request_container.get(BackupManager)

        # Verify it's a real SQLAlchemy session with expected methods
        assert hasattr(manager.db_session, "query")
        assert hasattr(manager.db_session, "commit")
        assert hasattr(manager.db_session, "rollback")
        assert hasattr(manager.db_session, "close")


def test_backup_manager_session_is_fresh_per_request(di_container):
    """Test that each request scope gets a fresh session."""
    # First request
    with di_container() as request_container1:
        manager1 = request_container1.get(BackupManager)
        session1 = manager1.db_session

    # Second request
    with di_container() as request_container2:
        manager2 = request_container2.get(BackupManager)
        session2 = manager2.db_session

    # Should be different session instances
    assert session1 is not session2
